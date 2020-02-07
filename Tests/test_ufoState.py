import pathlib
import shutil
from fontTools.pens.recordingPen import RecordingPointPen
from fontTools.ufoLib import UFOReader
from fontTools.ufoLib.glifLib import Glyph
from fontgoggles.font.ufoFont import UFOState
from fontgoggles.compile.ufoCompiler import fetchCharacterMappingAndAnchors
from testSupport import getFontPath


def test_getUpdateInfo(tmpdir):
    ufoSource = getFontPath("MutatorSansBoldWideMutated.ufo")
    ufoPath = shutil.copytree(ufoSource, tmpdir / "test.ufo")
    reader = UFOReader(ufoPath, validate=False)
    glyphSet = reader.getGlyphSet()
    cmap, unicodes, anchors = fetchCharacterMappingAndAnchors(glyphSet, ufoPath)

    state1 = UFOState(reader, glyphSet, getAnchors=lambda: anchors, getUnicodes=lambda: unicodes)

    feaPath = pathlib.Path(reader.fs.getsyspath("/features.fea"))
    feaPath.touch()

    state2 = state1.newState()
    needsFeaturesUpdate, needsGlyphUpdate, needsInfoUpdate, needsCmapUpdate = state2.getUpdateInfo()
    assert needsFeaturesUpdate
    assert not needsGlyphUpdate
    assert not needsInfoUpdate
    assert not needsCmapUpdate

    infoPath = pathlib.Path(reader.fs.getsyspath("/fontinfo.plist"))
    infoPath.touch()

    state3 = state2.newState()
    needsFeaturesUpdate, needsGlyphUpdate, needsInfoUpdate, needsCmapUpdate = state3.getUpdateInfo()
    assert not needsFeaturesUpdate
    assert not needsGlyphUpdate
    assert needsInfoUpdate
    assert not needsCmapUpdate

    glyph = Glyph("A", None)
    ppen = RecordingPointPen()
    glyphSet.readGlyph("A", glyph, ppen)
    glyph.anchors[0]["x"] = 123
    glyphSet.writeGlyph("A", glyph, ppen.replay)

    state4 = state3.newState()
    needsFeaturesUpdate, needsGlyphUpdate, needsInfoUpdate, needsCmapUpdate = state4.getUpdateInfo()
    assert needsFeaturesUpdate
    assert needsGlyphUpdate
    assert not needsInfoUpdate
    assert not needsCmapUpdate

    glyph = Glyph("A", None)
    ppen = RecordingPointPen()
    glyphSet.readGlyph("A", glyph, ppen)
    glyph.unicodes = [123]
    glyphSet.writeGlyph("A", glyph, ppen.replay)

    state5 = state4.newState()
    needsFeaturesUpdate, needsGlyphUpdate, needsInfoUpdate, needsCmapUpdate = state5.getUpdateInfo()
    assert not needsFeaturesUpdate
    assert needsGlyphUpdate
    assert not needsInfoUpdate
    assert needsCmapUpdate

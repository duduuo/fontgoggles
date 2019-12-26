import AppKit
from vanilla import *
from fontTools.misc.arrayTools import offsetRect, scaleRect
from fontgoggles.mac.drawing import *
from fontgoggles.mac.misc import textAlignments
from fontgoggles.misc.decorators import delegateProperty, hookedProperty, suppressAndLogException
from fontgoggles.misc.rectTree import RectTree


class FGGlyphLineView(AppKit.NSView):

    def _scheduleRedraw(self):
        self.setNeedsDisplay_(True)

    selected = hookedProperty(_scheduleRedraw)
    align = hookedProperty(_scheduleRedraw)

    def init(self):
        self = super().init()
        self.vertical = 0  # 0, 1: it will also be an index into (x, y) tuples
        self.selected = False
        self.align = "left"
        self.unitsPerEm = 1000  # We need a non-zero default, proper value will be set later
        self._glyphs = None
        self._rectTree = None
        self._selection = None
        self._endPos = (0, 0)
        return self

    def isOpaque(self):
        return True

    def setGlyphs_endPos_upm_(self, glyphs, endPos, unitsPerEm):
        self._glyphs = glyphs
        self._endPos = endPos
        self.unitsPerEm = unitsPerEm
        rectIndexList = [(gi.bounds, index) for index, gi in enumerate(glyphs) if gi.bounds is not None]
        self._rectTree = RectTree.fromSeq(rectIndexList)
        self._selection = set()
        self.setNeedsDisplay_(True)

    @property
    def minimumExtent(self):
        return self.margin * 2 + abs(self._endPos[self.vertical]) * self.scaleFactor

    @property
    def scaleFactor(self):
        itemSize = self.frame().size[1 - self.vertical]
        return 0.7 * itemSize / self.unitsPerEm

    @property
    def margin(self):
        itemSize = self.frame().size[1 - self.vertical]
        return 0.1 * itemSize

    @property
    def origin(self):
        endPos = abs(self._endPos[self.vertical]) * self.scaleFactor
        margin = self.margin
        align = self.align
        itemExtent = self.frame().size[self.vertical]
        itemSize = self.frame().size[1 - self.vertical]
        if align == "right" or align == "bottom":
            pos = itemExtent - margin - endPos
        elif align == "center":
            pos = (itemExtent - endPos) / 2
        else:  # align == "left"
            pos = margin
        if not self.vertical:
            return pos, 0.25 * itemSize  # TODO: something with hhea/OS/2 ascender/descender
        else:
            return 0.5 * itemSize, itemExtent - pos  # TODO: something with vhea ascender/descender

    @suppressAndLogException
    def drawRect_(self, rect):
        backgroundColor = AppKit.NSColor.textBackgroundColor()
        foregroundColor = AppKit.NSColor.textColor()

        if self.selected:
            # Blend color could be a pref from the systemXxxxColor colors
            backgroundColor = backgroundColor.blendedColorWithFraction_ofColor_(0.3, AppKit.NSColor.systemOrangeColor())

        backgroundColor.set()
        AppKit.NSRectFill(rect)

        if not self._glyphs:
            return

        dx, dy = self.origin

        invScale = 1 / self.scaleFactor
        rect = rectFromNSRect(rect)
        rect = scaleRect(offsetRect(rect, -dx, -dy), invScale, invScale)

        translate(dx, dy)
        scale(self.scaleFactor)

        foregroundColor.set()
        lastPosX = lastPosY = 0
        for index in self._rectTree.iterIntersections(rect):
            gi = self._glyphs[index]
            selected = self._selection and index in self._selection
            if selected:
                AppKit.NSColor.redColor().set()
            posX, posY = gi.pos
            translate(posX - lastPosX, posY - lastPosY)
            lastPosX, lastPosY = posX, posY
            gi.path.fill()
            if selected:
                AppKit.NSColor.textColor().set()

    @suppressAndLogException
    def mouseDown_(self, event):
        if self._rectTree is None:
            return
        x, y = self.convertPoint_fromView_(event.locationInWindow(), None)
        scaleFactor = self.scaleFactor
        dx, dy = self.origin
        x -= dx
        y -= dy
        x /= scaleFactor
        y /= scaleFactor

        indices = list(self._rectTree.iterIntersections((x, y, x, y)))
        if not indices:
            self.selected = not self.selected
            return
        if len(indices) == 1:
            index = indices[0]
        else:
            # There are multiple candidates. Let's do point-inside testing,
            # and take the last hit, if any. Fall back to the last.
            for index in reversed(indices):
                gi = self._glyphs[index]
                posX, posY = gi.pos
                if gi.path.containsPoint_((x - posX, y - posY)):
                    break
            else:
                index = indices[-1]

        if index is not None:
            if self._selection is None:
                self._selection = set()
            newSelection = {index}
            if newSelection == self._selection:
                newSelection = set()  # deselect
            diffSelection = self._selection ^ newSelection
            self._selection = newSelection
            for index in diffSelection:
                bounds = self._glyphs[index].bounds
                if bounds is None:
                    continue
                bounds = offsetRect(scaleRect(bounds, scaleFactor, scaleFactor), dx, dy)
                self.setNeedsDisplayInRect_(nsRectFromRect(bounds))


class GlyphLine(Group):
    nsViewClass = FGGlyphLineView
    vertical = delegateProperty("_nsObject")


class FGFontListView(AppKit.NSView):

    @suppressAndLogException
    def magnifyWithEvent_(self, event):
        pass
        # scrollView = self.enclosingScrollView()
        # clipView = scrollView.contentView()
        # if event.phase() == AppKit.NSEventPhaseBegan:
        #     self._savedClipBounds = clipView.bounds()
        # if event.phase() == AppKit.NSEventPhaseEnded:
        #     origin = clipView.bounds().origin
        #     fontList = self.vanillaWrapper()
        #     fontList.resizeFontItems(fontList.itemSize * scrollView.magnification())

        #     scrollView.setMagnification_(1.0)  #centeredAtPoint_
        #     # self._savedClipBounds.origin = clipView.bounds().origin
        #     bounds = clipView.bounds()
        #     bounds.origin = origin
        #     # clipView.setBounds_(bounds)
        #     del self._savedClipBounds
        # else:
        #     super().magnifyWithEvent_(event)


fontItemNameTemplate = "fontItem_{index}"


class FontList(Group):

    nsViewClass = FGFontListView

    def __init__(self, fontKeys, width, itemSize):
        super().__init__((0, 0, width, 900))
        self.vertical = 0  # 0, 1: it will also be an index into (x, y) tuples
        self.itemSize = itemSize
        self.align = "left"
        y = 0
        for index, fontKey in enumerate(fontKeys):
            fontItemName = fontItemNameTemplate.format(index=index)
            fontItem = FontItem((0, y, 0, itemSize), fontKey)
            setattr(self, fontItemName, fontItem)
            y += itemSize
        self.setPosSize((0, 0, width, y))

    @property
    def width(self):
        return self.getPosSize()[2]

    @width.setter
    def width(self, newWidth):
        x, y, w, h = self.getPosSize()
        self.setPosSize((x, y, newWidth, h))

    @property
    def height(self):
        return self.getPosSize()[3]

    @height.setter
    def height(self, newHeight):
        x, y, w, h = self.getPosSize()
        self.setPosSize((x, y, w, newHeight))

    @hookedProperty
    def align(self):
        # self.align has already been set to the new value
        for fontItem in self.iterFontItems():
            fontItem.align = self.align

        scrollView = self._nsObject.enclosingScrollView()
        if scrollView is None:
            return

        ourBounds = self._nsObject.bounds()
        clipView = scrollView.contentView()
        clipBounds = clipView.bounds()
        if clipBounds.size.width >= ourBounds.size.width:
            # Handled by AligningScrollView
            return

        sizeDiff = ourBounds.size.width - clipBounds.size.width
        atLeft = abs(clipBounds.origin.x) < 2
        atRight = abs(clipBounds.origin.x - sizeDiff) < 2
        atCenter = abs(clipBounds.origin.x - sizeDiff / 2) < 2
        if self.align == "left":
            if atRight or atCenter:
                clipBounds.origin.x = 0
        elif self.align == "center":
            if atLeft or atRight:
                clipBounds.origin.x = sizeDiff / 2
        elif self.align == "right":
            if atLeft or atCenter:
                clipBounds.origin.x = sizeDiff
        clipView.setBounds_(clipBounds)

    def iterFontItems(self):
        index = 0
        while True:
            item = getattr(self, fontItemNameTemplate.format(index=index), None)
            if item is None:
                break
            yield item
            index += 1

    def setVertical(self, vertical):
        if self.vertical == vertical:
            return
        self.vertical = vertical
        pos = [0, 0]
        for fontItem in self.iterFontItems():
            fontItem.vertical = vertical
            fontItem.fileNameLabel.setPosSize(fontItem.getFileNameLabelPosSize())
            fontItem.fileNameLabel._nsObject.rotateByAngle_([-90, 90][vertical])
            x, y, w, h = fontItem.getPosSize()
            w, h = h, w
            fontItem.setPosSize((*pos, w, h))
            pos[1 - vertical] += self.itemSize
        x, y, w, h = self.getPosSize()
        w, h = h, w
        self.setPosSize((x, y, w, h))
        self._nsObject.setNeedsDisplay_(True)

    @suppressAndLogException
    def resizeFontItems(self, itemSize):
        scaleFactor = itemSize / self.itemSize
        self.itemSize = itemSize
        pos = [0, 0]
        for fontItem in self.iterFontItems():
            x, y, *wh = fontItem.getPosSize()
            wh[1 - self.vertical] = itemSize
            fontItem.setPosSize((*pos, *wh))
            pos[1 - self.vertical] += itemSize

        # calculate the center of our clip view in relative doc coords
        # so we can set the scroll position and zoom in/out "from the middle"
        x, y, w, h = self.getPosSize()
        clipView = self._nsObject.superview()
        (cx, cy), (cw, ch) = clipView.bounds()
        cx += cw / 2
        cy -= ch / 2
        cx /= w
        cy /= h

        if not self.vertical:
            self.setPosSize((x, y, w * scaleFactor, pos[1]))
            cx *= w * scaleFactor
            cy *= pos[1]
        else:
            self.setPosSize((x, y, pos[0], h * scaleFactor))
            cx *= pos[0]
            cy *= h * scaleFactor
        cx -= cw / 2
        cy += ch / 2
        clipBounds = clipView.bounds()
        clipBounds.origin = (cx, cy)
        clipView.setBounds_(clipBounds)


class FontItem(Group):

    vertical = delegateProperty("glyphLineView")

    def __init__(self, posSize, fontKey):
        super().__init__(posSize)
        # self._nsObject.setWantsLayer_(True)
        # self._nsObject.setCanDrawSubviewsIntoLayer_(True)
        self.glyphLineView = GlyphLine((0, 0, 0, 0))
        self.fileNameLabel = UnclickableTextBox(self.getFileNameLabelPosSize(), "", sizeStyle="small")
        self.fileNameLabel._nsObject.cell().setLineBreakMode_(AppKit.NSLineBreakByTruncatingMiddle)
        self.progressSpinner = ProgressSpinner((10, 20, 25, 25))
        self.setFontKey(fontKey)

    def setIsLoading(self, isLoading):
        if isLoading:
            self.progressSpinner.start()
        else:
            self.progressSpinner.stop()

    def setFontKey(self, fontKey):
        fontPath, fontNumber = fontKey
        fileNameLabel = f"{fontPath.name}"
        if fontNumber:
            fileNameLabel += f"#{fontNumber}"
        self.fileNameLabel.set(fileNameLabel)
        self.fileNameLabel._nsObject.setToolTip_(str(fontPath))

    def setGlyphs(self, glyphs, endPos, unitsPerEm):
        self.glyphLineView._nsObject.setGlyphs_endPos_upm_(glyphs, endPos, unitsPerEm)

    @property
    def minimumExtent(self):
        return self.glyphLineView._nsObject.minimumExtent

    @property
    def align(self):
        return self.glyphLineView._nsObject.align

    @align.setter
    def align(self, value):
        nsAlignment = textAlignments.get(value, textAlignments["left"])
        self.fileNameLabel._nsObject.cell().setAlignment_(nsAlignment)
        self.glyphLineView._nsObject.align = value

    def getFileNameLabelPosSize(self):
        if self.vertical:
            return (2, 10, 17, -10)
        else:
            return (10, 0, -10, 17)


class FGUnclickableTextField(AppKit.NSTextField):

    def hitTest_(self, point):
        return None


class UnclickableTextBox(TextBox):

    """This TextBox sublass is transparent for clicks."""

    nsTextFieldClass = FGUnclickableTextField
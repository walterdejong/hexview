#
#   vga.py  WJ116
#

'''emulate VGA text mode screen in curses (well, sort of)'''

import curses
import os
import sys

# the 'stdscr' variable
STDSCR = None
# the VGA screen
SCREEN = None

# color codes
(BLACK,
 BLUE,
 GREEN,
 CYAN,
 RED,
 MAGENTA,
 YELLOW,
 WHITE) = range(0, 8)
BOLD = 8

FGCOLOR = WHITE
FGCOLOR_BOLD = True
BGCOLOR = BLACK

# list of curses color codes
# initialized during init() (because curses is crazy; it doesn't have
# any of it's static constants/symbols until you initialize it)
CURSES_COLORS = None

# maps fg:bg colors to curses color pairs
COLOR_PAIRS = {}
COLOR_PAIR_IDX = 0

# current curses color
CURSES_COLOR = 0

# key codes
# in cwin there are strings; translated by getch()
# There is no support for F-keys! Functions keys are evil on Macs
KEY_ESC = 'ESC'
KEY_RETURN = 'RETURN'
KEY_TAB = 'TAB'
KEY_BTAB = 'BTAB'
KEY_LEFT = 'LEFT'
KEY_RIGHT = 'RIGHT'
KEY_UP = 'UP'
KEY_DOWN = 'DOWN'
KEY_PAGEUP = 'PAGEUP'
KEY_PAGEDOWN = 'PAGEDOWN'
KEY_HOME = 'HOME'
KEY_END = 'END'
KEY_DEL = 'DEL'
KEY_BS = 'BS'

KEY_TABLE = {'0x1b': KEY_ESC, '0x0a': KEY_RETURN,
             '0x09': KEY_TAB, '0x161': KEY_BTAB,
             '0x102': KEY_DOWN, '0x103': KEY_UP,
             '0x104': KEY_LEFT, '0x105': KEY_RIGHT,
             '0x152': KEY_PAGEDOWN, '0x153': KEY_PAGEUP,
             '0x106': KEY_HOME, '0x168': KEY_END,
             '0x14a': KEY_DEL, '0x107': KEY_BS, '0x7f': KEY_BS}

# debug messages
DEBUG_LOG = []


def debug(msg):
    '''keep message in debug log'''

    DEBUG_LOG.append(msg)


def dump_debug():
    '''dump out the debug log'''

    global DEBUG_LOG

    for msg in DEBUG_LOG:
        print msg

    DEBUG_LOG = []


class ScreenBuffer(object):
    '''text screen buffer'''

    def __init__(self, x, y, w, h):
        '''initialize instance'''

        assert x >= 0
        assert y >= 0
        assert w > 0
        assert h > 0

        self.x = x
        self.y = y
        self.w = w
        self.h = h
        # we add some space for the shadow
        self.bufw = w + 2
        self.bufh = h + 1
        self.textbuf = bytearray(self.bufw * self.bufh)
        self.colorbuf = bytearray(self.bufw * self.bufh)
        # saved buffers
        self.origtext = bytearray(self.bufw * self.bufh)
        self.origcolor = bytearray(self.bufw * self.bufh)

        self.fg = None
        self.bg = None
        self.bold = None
        self.color = None
        self.set_color(WHITE, BLACK, bold=False)

        self.clear()

    def save_background(self):
        '''save background'''

        # do clipping
        w = self.bufw
        if self.x + w > SCREEN.w:
            w = SCREEN.w - self.x
            if w <= 0:
                return

        h = self.bufh
        if self.y + h > SCREEN.h:
            h = SCREEN.h - self.y
            if h <= 0:
                return

        for j in xrange(0, h):
            src = (self.y + j) * SCREEN.bufw + self.x
            dst = j * w
            memmove(self.origtext, dst, SCREEN.textbuf, src, w)
            memmove(self.origcolor, dst, SCREEN.colorbuf, src, w)

    def restore_background(self):
        '''restore background'''

        for j in xrange(0, self.bufh):
            dst = (self.y + j) * SCREEN.bufw + self.x
            src = j * self.bufw
            memmove(SCREEN.textbuf, dst, self.origtext, src, self.bufw)
            memmove(SCREEN.colorbuf, dst, self.origcolor, src, self.bufw)
            # update the curses screen (slower loop)
            for i in xrange(0, self.bufw):
                ch = SCREEN.textbuf[dst + i]
                if ch & 0x80:
                    # restore special curses attribute
                    ch &= 0x7f
                    ch |= 0x400000
                color = SCREEN.colorbuf[dst + i]
                STDSCR.addch(self.y + j, self.x + i, ch,
                             self.curses_color(color))

    def close(self):
        '''close the window'''

        self.restore_background()

    def curses_color(self, vga):
        '''Returns curses color attributes for given VGA color'''

        pair = '%02x' % (vga & ~BOLD)
        color = curses.color_pair(COLOR_PAIRS[pair])

        if vga & BOLD == BOLD:
            color |= curses.A_BOLD

        return color

    def set_color(self, fg, bg, bold=True):
        '''change current color'''

        self.fg = fg
        self.bg = bg
        self.bold = bold
        self.color = vga_color(fg, bg, bold)
        self._make_curses_color()

    def _make_curses_color(self):
        '''make curses color pair'''

        global CURSES_COLOR, COLOR_PAIR_IDX

        pair = '%02x' % ((self.bg << 4) | self.fg)
        if pair not in COLOR_PAIRS:
            assert COLOR_PAIR_IDX < curses.COLOR_PAIRS

            # make new curses color pair
            COLOR_PAIR_IDX += 1
            curses.init_pair(COLOR_PAIR_IDX, CURSES_COLORS[self.fg],
                             CURSES_COLORS[self.bg])
            COLOR_PAIRS[pair] = COLOR_PAIR_IDX

        CURSES_COLOR = curses.color_pair(COLOR_PAIRS[pair])

        if self.bold:
            CURSES_COLOR |= curses.A_BOLD

        # use this color
        STDSCR.attrset(CURSES_COLOR)

    def clear(self, ch=' '):
        '''fill buffer with byte ch'''

        if isinstance(ch, str):
            ch = ord(ch)

        fillchar = ch & 0x7f
        if ch > 0x400000:
            fillchar |= 0x80

        for i in xrange(0, len(self.textbuf)):
            self.textbuf[i] = fillchar
            self.colorbuf[i] = self.color

    def putch(self, x, y, ch):
        '''put character at x, y'''

        assert x >= 0
        assert y >= 0

        # do clipping
        if x >= self.w:
            return

        if y >= self.h:
            return

        if isinstance(ch, str):
            ch = ord(ch)

        offset = y * self.bufw + x

        self.textbuf[offset] = ch & 0x7f
        if ch > 0x400000:
            self.textbuf[offset] |= 0x80
        self.colorbuf[offset] = self.color

        STDSCR.addch(self.y + y, self.x + x, ch)

    def __getitem__(self, idx):
        '''Returns tuple: (ch, color) at x, y'''

        x, y = idx

        assert x >= 0
        assert y >= 0

        assert x < self.w
        assert y < self.h

        offset = self.bufw * y + x
        return (self.textbuf[offset], self.colorbuf[offset])

    def __setitem__(self, idx, item):
        '''put a (ch, color) tuple into the buffer at x, y'''

        x, y = idx

        assert x >= 0
        assert y >= 0

        # do clipping
        if x >= self.w:
            return

        if y >= self.h:
            return

        if isinstance(item, tuple):
            ch, color = item
        else:
            ch = item
            color = self.color

        if isinstance(ch, str):
            ch = ord(ch)

        offset = y * self.bufw + x
        self.textbuf[offset] = ch & 0x7f
        if ch > 0x400000:
            self.textbuf[offset] |= 0x80
        self.colorbuf[offset] = self.color

        curses_color = self.curses_color(color)
        STDSCR.addch(self.y + y, self.x + x, ch, curses_color)

    def put(self, x, y, msg):
        '''write message at x, y'''

        assert x >= 0
        assert y >= 0

        # clip message
        if x >= self.w:
            return

        if y >= self.h:
            return

        if x + len(msg) > self.w:
            msg = msg[:self.w - (x + len(msg))]
            if not msg:
                return

        offset = y * self.bufw + x
        for ch in msg:
            self.textbuf[offset] = ord(ch)
            self.colorbuf[offset] = self.color
            offset += 1

        STDSCR.addstr(self.y + y, self.x + x, msg)

    def get(self, x, y, w):
        '''Returns string at x, y for w characters'''

        # FIXME do clipping
        return str(self.textbuf[y * self.bufw + x:y * self.w + x + w])

    def getattr(self, x, y, w):
        '''Returns bytearray of colors at x, y'''

        # FIXME do clipping
        return self.colorbuf[y * self.bufw + x:y * self.w + x + w]

    def fillrect(self, x=0, y=0, w=0, h=0, ch=' '):
        '''draw filled rectangle'''

        assert x >= 0
        assert y >= 0

        if w == 0:
            w = self.w
        assert w > 0

        if h == 0:
            h = self.h
        assert h > 0

        # do clipping
        if x >= w:
            return

        if y >= h:
            return

        if x + w > self.w:
            w = self.w - x
            if w <= 0:
                return

        if y + h > self.h:
            h = self.h - y
            if h <= 0:
                return

        if isinstance(ch, str):
            # make byte value
            ch = ord(ch)

        fillchar = ch & 0x7f
        if ch > 0x400000:
            fillchar |= 0x80

        # fillrect by drawing a bunch of hlines
        for j in xrange(0, h):
            offset = (y + j) * self.bufw + x
            for _i in xrange(w):
                self.textbuf[offset] = fillchar
                self.colorbuf[offset] = self.color
                offset += 1

            STDSCR.hline(self.y + y + j, self.x + x, ch, w)

    def hline(self, x, y, w=0, ch=None):
        '''draw horizontal line'''

        assert x >= 0
        assert y >= 0

        if w == 0:
            w = self.w
        assert w > 0

        # do clipping
        if x >= self.w:
            return

        if y >= self.h:
            return

        if x + w > self.w:
            w = self.w - x
            if w <= 0:
                return

        if ch is None:
            ch = curses.ACS_HLINE

        elif isinstance(ch, str):
            # make byte value
            ch = ord(ch)

        fillchar = ch & 0x7f
        if ch > 0x400000:
            fillchar |= 0x80

        offset = y * self.bufw + x
        for i in xrange(w):
            self.textbuf[offset + i] = fillchar
            self.colorbuf[offset + i] = self.color

        STDSCR.hline(self.y + y, self.x + x, ch, w)

    def vline(self, x, y, h=0, ch=None):
        '''draw vertical line'''

        assert x >= 0
        assert y >= 0

        if h == 0:
            h = self.h
        assert h > 0

        # do clipping
        if x >= self.w:
            return

        if y >= self.h:
            return

        if y + h > self.h:
            h = self.h - y
            if h <= 0:
                return

        if ch is None:
            ch = curses.ACS_VLINE

        elif isinstance(ch, str):
            # make byte value
            ch = ord(ch)

        fillchar = ch & 0x7f
        if ch > 0x400000:
            fillchar |= 0x80

        offset = y * self.bufw + x
        for _j in xrange(h):
            self.textbuf[offset] = fillchar
            self.colorbuf[offset] = self.color
            offset += self.bufw

        STDSCR.vline(self.y + y, self.x + x, ch, h)

    def border(self, x=0, y=0, w=0, h=0):
        '''draw border lines'''

        assert x >= 0
        assert y >= 0

        if w == 0:
            w = self.w
        assert w > 0

        if h == 0:
            h = self.h
        assert h > 0

        # do clipping
        if x >= self.w:
            return

        if y >= self.h:
            return

        clipx = False
        if x + w > self.w:
            clipx = True
            w = self.w - x
            if w <= 0:
                return

        clipy = False
        if y + h > self.h:
            clipy = True
            h = self.h - y
            if h <= 0:
                return

        if clipx:
            width = w - 1
        else:
            width = w - 2

        if clipy:
            height = h - 1
        else:
            height = h - 2

        # top
        self.putch(x, y, curses.ACS_ULCORNER)
        self.hline(x + 1, y, width)
        if not clipx:
            self.putch(x + w - 1, y, curses.ACS_URCORNER)

        # left
        self.vline(x, y + 1, height)

        # right
        if not clipx:
            self.vline(x + w - 1, y + 1, height)

        # bottom
        if clipy:
            return

        y += h - 1
        self.putch(x, y, curses.ACS_LLCORNER)
        self.hline(x + 1, y, width)
        if not clipx:
            self.putch(x + w - 1, y, curses.ACS_LRCORNER)

    def shadow(self):
        '''draw a shadow'''

        saved = self.save_color()
        self.set_color(BLACK, BLACK, bold=True)

        # clip off screen
        shadow_w = self.w + 2
        if self.x + shadow_w > SCREEN.w:
            shadow_w = SCREEN.w - self.x
        shadow_w -= self.w
        if shadow_w > 0:
            # draw vertical shadow lines on right side
            for j in xrange(self.h):
                offset = (j + 1) * self.bufw + self.w
                ch = self.origtext[offset]
                if ch & 0x80:
                    ch &= 0x7f
                    ch |= 0x400000

                self.colorbuf[offset] = self.color
                # redraw text in shadow color
                STDSCR.addch(self.y + 1 + j, self.x + self.w, ch)

                if shadow_w > 1:
                    # one more vertical shadow strip
                    offset += 1
                    ch = self.origtext[offset]
                    if ch & 0x80:
                        ch &= 0x7f
                        ch |= 0x400000

                    self.colorbuf[offset] = self.color
                    STDSCR.addch(self.y + 1 + j, self.x + self.w + 1, ch)

        # clip against bottom of screen
        if self.y + 1 + self.h > SCREEN.h:
            self.restore_color(saved)
            return

        # clip off screen
        w = self.w
        if self.x + 2 + w > SCREEN.w:
            w = SCREEN.w - (self.x + 2)

        # draw horizontal shadow line under buffer rect
        offset = self.h * self.bufw + 2
        for i in xrange(w):
            ch = self.origtext[offset + i]
            if ch & 0x80:
                ch &= 0x7f
                ch |= 0x400000

            self.colorbuf[offset + i] = self.color
            # redraw text in shadow color
            STDSCR.addch(self.y + self.h, self.x + 2 + i, ch)

        self.restore_color(saved)

    def save_color(self):
        '''Returns tuple with all saved colors'''

        return (self.fg, self.bg, self.bold, self.color, CURSES_COLOR)

    def restore_color(self, saved):
        '''restore saved color set'''

        global CURSES_COLOR

        assert len(saved) == 5

        self.fg = saved[0]
        self.bg = saved[1]
        self.bold = saved[2]
        self.color = saved[3]
        CURSES_COLOR = saved[4]

        # set the curses color
        STDSCR.attrset(CURSES_COLOR)



def vga_color(fg, bg, bold=True):
    '''Returns VGA color byte'''

    assert fg >= 0 and fg < 8
    assert bg >= 0 and bg < 8

    if bold:
        return fg | BOLD | (bg << 4)
    else:
        return fg | (bg << 4)


def memmove(dst, dst_idx, src, src_idx, count):
    '''Copy from src to dst bytearray
    Note that first argument is destination
    '''

    assert isinstance(dst, bytearray)
    assert isinstance(src, bytearray)
    assert dst_idx >= 0
    assert src_idx >= 0
    assert count >= 0

    if count == 0:
        return

    dst[dst_idx:dst_idx + count] = src[src_idx:src_idx + count]


def init():
    '''initialize'''

    global STDSCR, SCREEN, CURSES_COLORS

    os.environ['ESCDELAY'] = '25'

    STDSCR = curses.initscr()
    curses.savetty()
    curses.start_color()
    curses.noecho()
    STDSCR.keypad(1)
    curses.raw()
    curses.curs_set(0)

    # init colors in same order as the color 'enums'
    CURSES_COLORS = (curses.COLOR_BLACK,
                     curses.COLOR_BLUE,
                     curses.COLOR_GREEN,
                     curses.COLOR_CYAN,
                     curses.COLOR_RED,
                     curses.COLOR_MAGENTA,
                     curses.COLOR_YELLOW,
                     curses.COLOR_WHITE)

    # make the SCREEN screenbuffer
    h, w = STDSCR.getmaxyx()
    SCREEN = ScreenBuffer(0, 0, w, h)
    SCREEN.set_color(BLACK, WHITE, bold=False)
    SCREEN.fillrect(0, 0, SCREEN.w, SCREEN.h, curses.ACS_CKBOARD)

    # odd ... screen must be refreshed at least once,
    # or things won't work as expected
    STDSCR.refresh()


def terminate():
    '''end the curses window mode'''

    if STDSCR is not None:
        curses.curs_set(1)
        curses.nocbreak()
        STDSCR.keypad(0)
        curses.echo()
        curses.resetty()
        curses.endwin()

    dump_debug()


def getch():
    '''get keyboard input
    Returns key as a string value
    '''

    # update the screen
#    curses.panel.update_panels()
    curses.doupdate()

    key = STDSCR.getch()

    ## DEBUG
    if key == 17:
        # Ctrl-Q is hardwired to bail out
        terminate()
        sys.exit(0)

    # TODO if key == KEY_RESIZE: resize_event() for all panels

    if key >= ord(' ') and key <= ord('~'):
        # ascii keys are returned as string
        return chr(key)

    skey = '0x%02x' % key
    if skey in KEY_TABLE:
        return KEY_TABLE[skey]

    if key >= 1 and key <= 26:
        # Ctrl-A to Ctrl-Z
        return 'Ctrl-' + chr(ord('@') + key)

    return skey


def unit_test():
    '''test program'''

    init()

    SCREEN.hline(0, 0, SCREEN.w, ' ')
    SCREEN.hline(0, SCREEN.h - 1, SCREEN.w, ' ')
    SCREEN.set_color(YELLOW, MAGENTA)
    SCREEN.set_color(YELLOW, RED)
    SCREEN.put(4, 0, ' Hello from vga.py ')

    SCREEN.set_color(BLACK, WHITE, bold=False)
    SCREEN.hline(0, 15, SCREEN.w)

    sb = ScreenBuffer(10, 10, 20, 10)
    sb.save_background()
    sb.set_color(BLACK, CYAN, bold=False)
    sb.fillrect()
    sb.border()
    sb.shadow()
    sb.put(4, 1, 'Hello from screenbuffer')

    color = vga_color(YELLOW, MAGENTA, bold=True)
    sb[2, 4] = ('W', color)
    sb[3, 4] = ('J', color)

    key = getch()

    sb.close()

    key = getch()

    terminate()



if __name__ == '__main__':
    unit_test()


# EOB

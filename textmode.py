#
#   textmode.py     WJ116
#

'''classes and routines for text mode screens'''

import curses
import os

# the curses stdscr
STDSCR = None

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

# list of curses color codes
# initialized during init() (because curses is crazy; it doesn't have
# any of it's static constants/symbols until you initialize it)
CURSES_COLORS = None
CURSES_COLORPAIRS = {}
CURSES_COLORPAIR_IDX = 0

# curses key codes get translated to strings by getch()
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


class ScreenBuf(object):
    '''a screen buffer consist of two planes:
    a text buffer and a color buffer
    The text buffer holds one byte per character in 7 bits ASCII
    If the 8th bit is set, it is a special character (eg. a curses line)
    The color buffer holds one byte per color
    encoded as (bg << 4) | bold | fg
    '''

    def __init__(self, w, h):
        '''initialize'''

        assert w > 0
        assert h > 0

        self.w = w
        self.h = h

        self.textbuf = bytearray(w * h)
        self.colorbuf = bytearray(w * h)

    def __getitem__(self, idx):
        '''Returns tuple: (ch, color) at idx
        idx may be an offset or tuple: (x, y) position

        Raises IndexError, ValueError on invalid index
        '''

        if isinstance(idx, int):
            offset = idx

        elif isinstance(idx, tuple):
            x, y = idx
            offset = self.w * y + x

        else:
            raise ValueError('invalid argument')

        ch = self.textbuf[offset]
        if ch > 0x7f:
            # special curses character
            ch &= 0x7f
            ch |= 0x400000
        else:
            # make string
            ch = chr(ch)

        color = self.colorbuf[offset]
        return ch, color

    def __setitem__(self, idx, value):
        '''put tuple: (ch, color) at idx
        idx may be an offset or tuple: (x, y) position

        Raises IndexError, ValueError on invalid index
        or ValueError on invalid value
        '''

        ch, color = value
        if isinstance(ch, str):
            ch = ord(ch)
        else:
            if ch > 0x400000:
                # special curses character
                ch &= 0x7f
                ch |= 0x80

        if isinstance(idx, int):
            offset = idx

        elif isinstance(idx, tuple):
            x, y = idx
            offset = self.w * y + x

        else:
            raise ValueError('invalid argument')

        self.textbuf[offset] = ch
        self.colorbuf[offset] = color

    def memmove(self, dst_idx, src_idx, num):
        '''copy num bytes at src_idx to dst_idx'''

        dst2 = dst_idx + num
        src2 = src_idx + num
        self.textbuf[dst_idx:dst2] = self.textbuf[src_idx:src2]
        self.colorbuf[dst_idx:dst2] = self.colorbuf[src_idx:src2]

    def copyrect(self, dx, dy, src, sx=0, sy=0, sw=0, sh=0):
        '''copy src rect sx,sy,sw,sh to dest self at dx,dy'''

        assert isinstance(src, ScreenBuf)
        assert dx >= 0
        assert dy >= 0
        assert sx >= 0
        assert sy >= 0

        if sw == 0:
            sw = src.w
        if sh == 0:
            sh = src.h

        if sw > self.w:
            sw = self.w
        if sh > self.h:
            sh = self.h

        assert sw > 0
        assert sh > 0

        # local function
        def copyline(dst, dx, dy, src, sx, sy, sw):
            '''copy line at sx,sy to dest dx,dy'''

            si = sy * src.w + sx
            di = dy * dst.w + dx
            dst.textbuf[di:di + sw] = src.textbuf[si:si + sw]
            dst.colorbuf[di:di + sw] = src.colorbuf[si:si + sw]

        # copy rect by copying line by line
        for j in xrange(0, sh):
            copyline(self, dx, dy + j, src, sx, sy + j, sw)



class Video(object):
    '''text mode video'''

    def __init__(self):
        '''initialize'''

        if STDSCR is None:
            init_curses()

        self.h, self.w = STDSCR.getmaxyx()
        self.screenbuf = ScreenBuf(self.w, self.h)
        self.color = video_color(WHITE, BLACK, bold=False)
        self.curses_color = curses_color(WHITE, BLACK, bold=False)

    def set_color(self, fg, bg, bold=True):
        '''set current color'''

        self.color = video_color(fg, bg, bold)
        self.curses_color = curses_color(fg, bg, bold)
        STDSCR.attrset(self.curses_color)

    def putch(self, x, y, ch, color=-1):
        '''put character at x, y'''

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        self.screenbuf[x, y] = (ch, color)
        STDSCR.addch(y, x, ch, attr)



def video_color(fg, bg, bold=True):
    '''Returns ScreenBuf color code'''

    assert fg >= 0 and fg < BOLD
    assert bg >= 0 and bg < BOLD

    if bold:
        return (bg << 4) | BOLD | fg
    else:
        return (bg << 4) | fg


def curses_color(fg, bg=None, bold=True):
    '''Returns curses colorpair index'''

    global CURSES_COLORPAIR_IDX

    if bg is None:
        # passed in only a combined color code
        color = fg
        fg = color & 3
        bg = color >> 4
        bold = (color & BOLD) == BOLD

    assert fg >= 0 and fg < BOLD
    assert bg >= 0 and bg < BOLD

    idx = '%02x' % ((bg << 4) | fg)
    if idx not in CURSES_COLORPAIRS:
        # make new curses color pair
        assert (CURSES_COLORPAIR_IDX >= 0 and
                CURSES_COLORPAIR_IDX < curses.COLOR_PAIRS - 1)
        CURSES_COLORPAIR_IDX += 1
        fg = CURSES_COLORS[fg]
        bg = CURSES_COLORS[bg]
        curses.init_pair(CURSES_COLORPAIR_IDX, fg, bg)
        CURSES_COLORPAIRS[idx] = CURSES_COLORPAIR_IDX

    color = curses.color_pair(CURSES_COLORPAIRS[idx])
    if bold:
        return color | curses.A_BOLD
    else:
        return color


def init_curses():
    '''initialize curses'''

    global STDSCR, CURSES_COLORS

    os.environ['ESCDELAY'] = '25'

    STDSCR = curses.initscr()
    curses.savetty()
    curses.start_color()
    curses.noecho()
    STDSCR.keypad(1)
    curses.raw()
    curses.curs_set(0)

    # init colors in same order as the color 'enums'
    # Sadly, curses.CODES do not exist until initscr() is done
    CURSES_COLORS = (curses.COLOR_BLACK,
                     curses.COLOR_BLUE,
                     curses.COLOR_GREEN,
                     curses.COLOR_CYAN,
                     curses.COLOR_RED,
                     curses.COLOR_MAGENTA,
                     curses.COLOR_YELLOW,
                     curses.COLOR_WHITE)

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
    '''test this module'''

    video = Video()
    video.set_color(YELLOW, MAGENTA)

    center_x = video.w / 2 - 1
    center_y = video.h / 2

    video.putch(center_x, center_y, 'W')
    video.putch(center_x + 1, center_y, 'J')

    getch()

    terminate()



if __name__ == '__main__':
    unit_test()


# EOB

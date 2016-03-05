#
#   textmode.py     WJ116
#

'''classes and routines for text mode screens'''

import curses
import os
import sys
import time

# the main video object
VIDEO = None

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

    # There are some asserts, but in general,
    # ScreenBuf shouldn't care about buffer overruns or clipping
    # because  a) that's a bug   b) performance   c) handled by class Video

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
        if ch == 0:
            # blank
            ch = ' '
        elif ch > 0x7f:
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
        elif ch > 0x400000:
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

    def puts(self, x, y, msg, color):
        '''write message into buffer at x, y'''

        offset = self.w * y + x
        for ch in msg:
            self.__setitem__(offset, (ch, color))
            offset += 1

    def hline(self, x, y, w, ch, color):
        '''repeat character horizontally'''

        if isinstance(ch, str):
            ch = ord(ch)
        elif ch > 0x400000:
            # special curses character
            ch &= 0x7f
            ch |= 0x80

        offset = self.w * y + x
        for _ in xrange(0, w):
            self.textbuf[offset] = ch
            self.colorbuf[offset] = color
            offset += 1

    def vline(self, x, y, h, ch, color):
        '''repeat character horizontally'''

        if isinstance(ch, str):
            ch = ord(ch)
        elif ch > 0x400000:
            # special curses character
            ch &= 0x7f
            ch |= 0x80

        offset = self.w * y + x
        for _ in xrange(0, h):
            self.textbuf[offset] = ch
            self.colorbuf[offset] = color
            offset += self.w

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

    def set_color(self, fg, bg=None, bold=True):
        '''set current color
        Returns the combined color code
        '''

        self.color = video_color(fg, bg, bold)
        self.curses_color = curses_color(fg, bg, bold)
        STDSCR.attrset(self.curses_color)
        return self.color

    def putch(self, x, y, ch, color=-1):
        '''put character at x, y'''

        # clipping
        if x < 0 or x >= self.w or y < 0 or y >= self.h:
            return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        self.screenbuf[x, y] = (ch, color)
        STDSCR.addch(y, x, ch, attr)

    def puts(self, x, y, msg, color=-1):
        '''write message at x, y'''

        # clip y
        if y < 0 or y >= self.h:
            return

        # clip x
        if x < 0:
            msg = msg[-x:]
            if not msg:
                return
            x = 0

        if x + len(msg) >= self.w:
            msg = msg[:self.w]
            if not msg:
                return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        self.screenbuf.puts(x, y, msg, color)
        STDSCR.addstr(y, x, msg, attr)

    def hline(self, x, y, w, ch, color=-1):
        '''draw horizontal line at x, y'''

        # clip y
        if y < 0 or y >= self.h:
            return

        # clip x
        if x < 0:
            w += x
            if w <= 0:
                return
            x = 0

        if x + w >= self.w:
            w = self.w - x
            if w <= 0:
                return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        self.screenbuf.hline(x, y, w, ch, color)
        if isinstance(ch, str):
            ch = ord(ch)
        STDSCR.hline(y, x, ch, w, attr)

    def vline(self, x, y, h, ch, color=-1):
        '''draw vertical line at x, y'''

        # clip x
        if x < 0 or x >= self.w:
            return

        # clip y
        if y < 0:
            h += y
            if h <= 0:
                return
            y = 0

        if y + h >= self.h:
            h = self.h - y
            if h <= 0:
                return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        self.screenbuf.vline(x, y, h, ch, color)
        if isinstance(ch, str):
            ch = ord(ch)
        STDSCR.vline(y, x, ch, h, attr)

    def fillrect(self, x, y, w, h, color=-1):
        '''draw rectangle at x, y'''

        # clip x
        if x < 0:
            w += x
            if w <= 0:
                return
            x = 0

        if x + w >= self.w:
            w = self.w - x
            if w <= 0:
                return

        # clip y
        if y < 0:
            h += y
            if h <= 0:
                return
            y = 0

        if y + h >= self.h:
            h = self.h - y
            if h <= 0:
                return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        # temporarily change the current curses color
        STDSCR.attrset(attr)

        for j in xrange(0, h):
            self.screenbuf.hline(x, y + j, w, ' ', color)
            STDSCR.hline(y + j, x, ' ', w)

        # restore curses color
        STDSCR.attrset(self.curses_color)

    def border_unoptimized(self, x, y, w, h, color=-1):
        '''draw rectangle border'''

        # unoptimized version

        # top
        self.hline(x + 1, y, w - 2, curses.ACS_HLINE, color)
        # left
        self.vline(x, y + 1, h - 2, curses.ACS_VLINE, color)
        # right
        self.vline(x + w - 1, y + 1, h - 2, curses.ACS_VLINE, color)
        # bottom
        self.hline(x + 1, y + h - 1, w - 2, curses.ACS_HLINE, color)

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        STDSCR.attrset(attr)

        # corners
        if x >= 0 and x < self.w:
            # top left corner
            if y >= 0 and y < self.h:
                self.screenbuf[x, y] = (curses.ACS_ULCORNER, color)
                STDSCR.addch(y, x, curses.ACS_ULCORNER)

            # bottom left corner
            by = y + h - 1
            if by >= 0 and by < self.h:
                self.screenbuf[x, by] = (curses.ACS_LLCORNER, color)
                STDSCR.addch(by, x, curses.ACS_LLCORNER)

        x += w - 1
        if x >= 0 and x < self.w:
            # top right corner
            if y >= 0 and y < self.h:
                self.screenbuf[x, y] = (curses.ACS_URCORNER, color)
                STDSCR.addch(y, x, curses.ACS_URCORNER)

            # bottom right corner
            by = y + h - 1
            if by >= 0 and by < self.h:
                self.screenbuf[x, by] = (curses.ACS_LRCORNER, color)
                STDSCR.addch(by, x, curses.ACS_LRCORNER)

        STDSCR.attrset(self.curses_color)

    def border(self, x, y, w, h, color=-1):
        '''draw rectangle border'''

        # unrolled version

        # clip x direction
        clipx = x
        clipw = w
        if clipx < 0:
            clipw += clipx
            if clipw <= 0:
                return
            clipx = 0

        if clipx + clipw >= self.w:
            clipw = self.w - clipx
            if clipw <= 0:
                return

        # clip y direction
        clipy = y
        cliph = h
        if clipy < 0:
            cliph += clipy
            if cliph <= 0:
                return
            clipy = 0

        if clipy + cliph >= self.h:
            cliph = self.h - clipy
            if cliph <= 0:
                return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        STDSCR.attrset(attr)

        # top
        if y >= 0 and y < self.h and clipw > 2:
            self.screenbuf.hline(clipx + 1, y, clipw - 2, curses.ACS_HLINE,
                                 color)
            STDSCR.hline(y, clipx + 1, curses.ACS_HLINE, clipw - 2)

        # left
        if x >= 0 and x < self.w and cliph > 2:
            self.screenbuf.vline(x, clipy + 1, cliph - 2, curses.ACS_VLINE,
                                 color)
            STDSCR.vline(clipy + 1, x, curses.ACS_VLINE, cliph - 2)

            # top left corner
            if y >= 0 and y < self.h:
                self.screenbuf[x, y] = (curses.ACS_ULCORNER, color)
                STDSCR.addch(y, x, curses.ACS_ULCORNER)

            # bottom left corner
            by = y + h - 1
            if by >= 0 and by < self.h:
                self.screenbuf[x, by] = (curses.ACS_LLCORNER, color)
                STDSCR.addch(by, x, curses.ACS_LLCORNER)

        # right
        x += w - 1
        if x >= 0 and x < self.w and cliph > 2:
            self.screenbuf.vline(x, clipy + 1, cliph - 2, curses.ACS_VLINE,
                                 color)
            STDSCR.vline(clipy + 1, x, curses.ACS_VLINE, cliph - 2)

            # top right corner
            if y >= 0 and y < self.h:
                self.screenbuf[x, y] = (curses.ACS_URCORNER, color)
                STDSCR.addch(y, x, curses.ACS_URCORNER)

            # bottom right corner
            by = y + h - 1
            if by >= 0 and by < self.h:
                self.screenbuf[x, by] = (curses.ACS_LRCORNER, color)
                STDSCR.addch(by, x, curses.ACS_LRCORNER)

        # bottom
        y += h - 1
        if y >= 0 and y < self.h and clipw > 2:
            self.screenbuf.hline(clipx + 1, y, clipw - 2, curses.ACS_HLINE,
                                 color)
            STDSCR.hline(y, clipx + 1, curses.ACS_HLINE, clipw - 2)

        STDSCR.attrset(self.curses_color)

    def color_hline(self, x, y, w, color=-1):
        '''draw horizontal color line'''

        # clip y
        if y < 0 or y >= self.h:
            return

        # clip x
        if x < 0:
            w += x
            if w <= 0:
                return
            x = 0

        if x + w >= self.w:
            w = self.w - x
            if w <= 0:
                return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        # get the character and redraw with color
        offset = self.w * y + x
        for i in xrange(0, w):
            ch, color = self.screenbuf[offset]
            self.screenbuf[offset] = (ch, color)
            offset += 1
            if isinstance(ch, str):
                ch = ord(ch)
            STDSCR.addch(y, x + i, ch, attr)

    def color_vline(self, x, y, h, color=-1):
        '''draw vertical colored line'''

        # clip x
        if x < 0 or x >= self.w:
            return

        # clip y
        if y < 0:
            h += y
            if h <= 0:
                return
            y = 0

        if y + h >= self.h:
            w = self.h - y
            if y <= 0:
                return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        # get the character and redraw with color
        offset = self.w * y + x
        for j in xrange(0, h):
            ch, color = self.screenbuf[offset]
            self.screenbuf[offset] = (ch, color)
            offset += self.w
            if isinstance(ch, str):
                ch = ord(ch)
            STDSCR.addch(y + j, x, ch, attr)



class Rect(object):
    '''represents a rectangle'''

    def __init__(self, x, y, w, h):
        '''initialize'''

        assert w > 0
        assert h > 0

        self.x = x
        self.y = y
        self.w = w
        self.h = h



class Window(object):
    '''represents a window'''

    OPEN = 1
    SHOWN = 2
    FOCUS = 4

    def __init__(self, x, y, w, h, fg=WHITE, bg=BLUE, bold=True, title=None,
                 border=True):
        '''initialize'''

        self.frame = Rect(x, y, w, h)
        self.color = video_color(fg, bg, bold)
        self.title = title
        self.has_border = border

        # bounds is the inner area; for view content
        self.bounds = Rect(x + 1, y + 1, w - 2, h - 2)

        # rect is the outer area; larger because of shadow
        self.rect = Rect(x, y, w + 2, h + 1)
        self.back = ScreenBuf(self.rect.w, self.rect.h)

        self.flags = 0
        self.title_color = self.border_color = self.color

    def set_color(self, fg, bg=None, bold=True):
        '''set color'''

        self.color = video_color(fg, bg, bold)

    def set_title_color(self, fg, bg=None, bold=True):
        '''set title color'''

        self.title_color = video_color(fg, bg, bold)

    def set_border_color(self, fg, bg=None, bold=True):
        '''set border color'''

        self.border_color = video_color(fg, bg, bold)

    def save_background(self):
        '''save the background'''

        self.back.copyrect(0, 0, VIDEO.screenbuf, self.rect.x, self.rect.y,
                           self.rect.w, self.rect.h)

    def restore_background(self):
        '''restore the background'''

        VIDEO.screenbuf.copyrect(self.rect.x, self.rect.y, self.back, 0, 0,
                                 self.rect.w, self.rect.h)
        # update the curses screen
        prev_color = None
        offset = VIDEO.w * self.rect.y + self.rect.x
        for j in xrange(0, self.rect.h):
            for i in xrange(0, self.rect.w):
                ch, color = VIDEO.screenbuf[offset]
                if isinstance(ch, str):
                    ch = ord(ch)

                if color != prev_color:
                    # only reset attr when the color did change
                    prev_color = color
                    attr = curses_color(color)

                offset += 1
                STDSCR.addch(self.rect.y + j, self.rect.x + i, ch, attr)
            offset += (VIDEO.w - self.rect.w)

    def open(self):
        '''open the window'''

        if self.flags & Window.OPEN:
            return

        self.flags |= Window.OPEN
        self.save_background()

    def close(self):
        '''close the window'''

        if not self.flags & Window.OPEN:
            return

        self.hide()
        self.flags &= ~Window.OPEN

    def show(self):
        '''open the window'''

        self.open()

        if self.flags & Window.SHOWN:
            return

        self.flags |= (Window.SHOWN | Window.FOCUS)
        self.draw()
        self.draw_cursor()

    def hide(self):
        '''hide the window'''

        if not self.flags & Window.SHOWN:
            return

        self.restore_background()
        self.flags &= ~(Window.SHOWN | Window.FOCUS)

    def gain_focus(self):
        '''event: we got focus'''

        self.flags |= Window.FOCUS
        self.draw_cursor()

    def loose_focus(self):
        '''event: focus lost'''

        self.flags &= ~Window.FOCUS
        self.draw_cursor()

    def draw(self):
        '''draw the window'''

        if not self.flags & Window.SHOWN:
            return

        # draw rect
        VIDEO.fillrect(self.frame.x, self.frame.y, self.frame.w, self.frame.h,
                       self.color)
        # draw border
        if self.has_border:
            VIDEO.border(self.frame.x, self.frame.y, self.frame.w,
                         self.frame.h, self.border_color)

        # draw frame shadow
        self.draw_shadow()

        # draw title
        if self.title is not None:
            title = ' ' + self.title + ' '
            x = (self.frame.w - len(title)) / 2
            VIDEO.puts(self.frame.x + x, self.frame.y, title,
                       self.title_color)

    def draw_shadow(self):
        '''draw shadow for frame rect'''

        if not self.flags & Window.SHOWN:
            return

        color = video_color(BLACK, BLACK, bold=True)

        # right side shadow vlines
        VIDEO.color_vline(self.frame.x + self.frame.w, self.frame.y + 1,
                          self.frame.h, color)
        VIDEO.color_vline(self.frame.x + self.frame.w + 1, self.frame.y + 1,
                          self.frame.h, color)
        # bottom shadow hline
        VIDEO.color_hline(self.frame.x + 2, self.frame.y + self.frame.h,
                          self.frame.w, color)

    def draw_cursor(self):
        '''draw cursor'''

        # override this method

#        if self.flags & Window.FOCUS:
#            ...
#        else:
#            ...
        pass

    def puts(self, x, y, msg, color=-1):
        '''print message in window
        Does not clear to end of line
        '''

        if not self.flags & Window.SHOWN:
            return

        # do window clipping
        if y < 0 or y >= self.bounds.h:
            return

        if x < 0:
            msg = msg[-x:]
            if not msg:
                return
            x = 0

        if x + len(msg) >= self.bounds.w:
            msg = msg[:self.bounds.w - x]
            if not msg:
                return

        if color == -1:
            color = self.color

        VIDEO.puts(self.bounds.x + x, self.bounds.y + y, msg, color)

    def cputs(self, x, y, msg, color=-1):
        '''print message in window
        Clear to end of line
        '''

        if not self.flags & Window.SHOWN:
            return

        # starts out the same as puts(), but then clears to EOL

        # do window clipping
        if y < 0 or y >= self.bounds.h:
            return

        if x < 0:
            msg = msg[-x:]
            if not msg:
                return
            x = 0

        if x + len(msg) >= self.bounds.w:
            msg = msg[:self.bounds.w - x]
            if not msg:
                return

        if color == -1:
            color = self.color

        VIDEO.puts(self.bounds.x + x, self.bounds.y + y, msg, color)
 
        # clear to end of line
        l = len(msg)
        w_eol = self.bounds.w - l - x
        if w_eol > 0:
            clear_eol = ' ' * w_eol
            VIDEO.puts(self.bounds.x + x + l, self.bounds.y + y,
                       clear_eol, color)



class TextWindow(Window):
    '''a window for displaying text'''

    def __init__(self, x, y, w, h, fg=WHITE, bg=BLUE, bold=True, title=None,
                 border=True, text=None, tabsize=4):
        '''initialize'''

        super(TextWindow, self).__init__(x, y, w, h, fg, bg, bold, title,
                                         border)
        if text is None:
            self.text = []
        else:
            self.text = text
        self.tabsize = tabsize

        self.top = 0
        self.cursor = 0
        self.cursor_color = video_color(WHITE, BLACK, bold=True)
        self.xoffset = 0
        self.scrollbar_y = 0
        self.scrollbar_h = 0

    def load(self, filename):
        '''load text file
        Raises IOError on error
        '''

        f = open(filename)
        with f:
            self.text = f.readlines()

        # strip newlines
        self.text = [x.rstrip() for x in self.text]

        # calc scrollbar
        if self.has_border and len(self.text) > 0:
            factor = float(self.bounds.h) / len(self.text)
            self.scrollbar_h = int(factor * self.bounds.h + 0.5)
            if self.scrollbar_h < 1:
                self.scrollbar_h = 1
            if self.scrollbar_h > self.bounds.h:
                self.scrollbar_h = self.bounds.h
#            self.update_scrollbar()

        if self.title is not None:
            self.title = os.path.basename(filename)

        # do a full draw because we loaded new text
        self.draw()

    def draw(self):
        '''draw the window'''

        if not self.flags & Window.SHOWN:
            return

        super(TextWindow, self).draw()
        self.draw_text()
        self.draw_scrollbar()

    def draw_text(self):
        '''draws the text content'''

        y = 0
        while y < self.bounds.h:
            if y == self.cursor:
                # draw_cursor() will be called by Window.draw()
                pass
            else:
                try:
                    self.printline(y)
                except IndexError:
                    break

            y += 1

    def draw_cursor(self):
        '''redraw the cursor line'''

        debug('TextWindow.draw_cursor()')
        if self.flags & Window.FOCUS:
            debug('focus: using cursor_color')
            color = self.cursor_color
        else:
            debug('focus: using default color')
            color = -1
        self.printline(self.cursor, color)

    def printline(self, y, color=-1):
        '''print a single line'''

        line = self.text[self.top + y]
        # replace tabs by spaces
        # This is because curses will display them too big
        line = line.replace('\t', ' ' * self.tabsize)
        # take x-scrolling into account
        line = line[self.xoffset:]
        self.cputs(0, y, line, color)

    def update_scrollbar(self):
        '''update scrollbar position'''

        if (not self.has_border or self.scrollbar_h <= 0 or
                not self.text):
            return

        old_y = self.scrollbar_y

        factor = float(self.bounds.h) / len(self.text)
        new_y = int((self.top + self.cursor) * factor + 0.5)
        if old_y != new_y:
            self.clear_scrollbar()
            self.scrollbar_y = new_y
            self.draw_scrollbar()

    def clear_scrollbar(self):
        '''erase scrollbar'''

        if not self.has_border or self.scrollbar_h <= 0:
            return

        y = self.scrollbar_y - self.scrollbar_h / 2
        if y < 0:
            y = 0
        if y > self.bounds.h - self.scrollbar_h:
            y = self.bounds.h - self.scrollbar_h

        VIDEO.vline(self.frame.x + self.frame.w - 1, self.bounds.y + y,
                    self.scrollbar_h, curses.ACS_VLINE, self.border_color)

    def draw_scrollbar(self):
        '''draw scrollbar'''

        if not self.has_border or self.scrollbar_h <= 0:
            return

        y = self.scrollbar_y - self.scrollbar_h / 2
        if y < 0:
            y = 0
        if y > self.bounds.h - self.scrollbar_h:
            y = self.bounds.h - self.scrollbar_h

        color = video_color(BLACK, WHITE, bold=False)
        VIDEO.vline(self.frame.x + self.frame.w - 1, self.bounds.y + y,
                    self.scrollbar_h, curses.ACS_CKBOARD, self.border_color)



def video_color(fg, bg=None, bold=True):
    '''Returns combined (ScreenBuf) color code'''

    if bg is None:
        # passed in only a combined color code
        return fg

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
        fg = color & 7
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

    # TODO if key == KEY_RESIZE: resize_event() for all windows

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


def init():
    '''initialize module'''

    global VIDEO

    VIDEO = Video()


def unit_test():
    '''test this module'''

    init()

    bgwin = Window(15, 20, 50, 16, fg=YELLOW, bg=RED, bold=True, title='Back')
    bgwin.show()
    bgwin.puts(0, 0, 'This is the back window')

    getch()

    win = TextWindow(10, 10, 50, 20, fg=WHITE, bg=BLUE, bold=True, title='Hello')
    win.set_title_color(YELLOW, BLUE, True)
    win.set_border_color(CYAN, BLUE, True)
    win.load('../../round.c')
    win.show()

    pinky = VIDEO.set_color(YELLOW, MAGENTA)
    VIDEO.set_color(YELLOW, GREEN)

    center_x = VIDEO.w / 2 - 1
    center_y = VIDEO.h / 2

    VIDEO.putch(center_x, center_y, 'W')
    VIDEO.putch(center_x + 1, center_y, 'J', pinky)

    getch()

    win.close()
    bgwin.cputs(0, 0, 'Bye!')

    getch()

    terminate()



if __name__ == '__main__':
    unit_test()


# EOB

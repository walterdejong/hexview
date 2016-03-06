#
#   textmode.py     WJ116
#

'''classes and routines for text mode screens'''

import curses
import os
import re
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

REGEX_HOTKEY = re.compile(r'.*<((Ctrl-)?[!-~])>.*$')

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

    # Note: the clipping methods work with relative coordinates
    # and don't care about the position of the Rect
    # ie. they don't use self.x, self.y
    # To obtain the absolute clipping coordinates, translate
    # the result by rect.x, rect.y

    def clip_point(self, x, y):
        '''clip point at relative x, y against rect
        Returns True if point is in the rect;
        if True then the point is visible
        '''

        return x >= 0 and x < self.w and y >= 0 and y < self.h

    def clip_hline(self, x, y, w):
        '''clip horizontal line against rect
        If visible, returns clipped tuple: True, x, y, w
        '''

        if y < 0 or y >= self.h:
            return False, -1, -1, -1

        if x < 0:
            w += x
            x = 0

        if x + w > self.w:
            w = self.w - x

        return True, x, y, w

    def clip_vline(self, x, y, h):
        '''clip vertical line against rect
        If visible, returns clipped tuple: True, x, y, h
        '''

        if x < 0 or x >= self.w:
            return False, -1, -1, -1

        if y < 0:
            h += y
            y = 0

        if y + h > self.h:
            h = self.h - y

        return True, x, y, h

    def clip_rect(self, x, y, w, h):
        '''clip rectangle against rect
        If visible, returns clipped tuple: True, x, y, w, h
        '''

        if x + w < 0 or x >= self.w or y + h < 0 or y >= self.h:
            return False, -1, -1, -1, -1

        if x < 0:
            w += x
            x = 0

        if x + w > self.w:
            w = self.w - x

        if y < 0:
            h += y
            y = 0

        if y + h > self.h:
            h = self.h - y

        return True, x, y, w, h



class Video(object):
    '''text mode video'''

    def __init__(self):
        '''initialize'''

        if STDSCR is None:
            init_curses()

        self.h, self.w = STDSCR.getmaxyx()
        self.screenbuf = ScreenBuf(self.w, self.h)
        self.rect = Rect(0, 0, self.w, self.h)
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
        if not self.rect.clip_point(x, y):
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

        visible, cx, cy, cw = self.rect.clip_hline(x, y, len(msg))
        if not visible:
            return

        # clip message
        if x < 0:
            msg = msg[-x:]
            if not msg:
                return

        if cw > len(msg):
            msg = msg[:cw]
            if not msg:
                return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        self.screenbuf.puts(cx, cy, msg, color)
        STDSCR.addstr(cy, cx, msg, attr)

    def hline(self, x, y, w, ch, color=-1):
        '''draw horizontal line at x, y'''

        visible, x, y, w = self.rect.clip_hline(x, y, w)
        if not visible:
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

        visible, x, y, h = self.rect.clip_vline(x, y, h)

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

        visible, x, y, w, h = self.rect.clip_rect(x, y, w, h)
        if not visible:
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

    def border(self, x, y, w, h, color=-1):
        '''draw rectangle border'''

        visible, cx, cy, cw, ch = self.rect.clip_rect(x, y, w, h)
        if not visible:
            return

        if color == -1:
            color = self.color
            attr = self.curses_color
        else:
            attr = curses_color(color)

        STDSCR.attrset(attr)

        # top
        if y >= 0 and y < self.h:
            self.screenbuf.hline(cx, y, cw, curses.ACS_HLINE, color)
            STDSCR.hline(y, cx, curses.ACS_HLINE, cw)

        # left
        if x >= 0 and x < self.w:
            self.screenbuf.vline(x, cy, ch, curses.ACS_VLINE, color)
            STDSCR.vline(cy, x, curses.ACS_VLINE, ch)

        # right
        rx = x + w - 1
        if rx >= 0 and rx < self.w:
            self.screenbuf.vline(rx, cy, ch, curses.ACS_VLINE, color)
            STDSCR.vline(cy, rx, curses.ACS_VLINE, ch)

        # bottom
        by = y + h - 1
        if by >= 0 and by < self.h:
            self.screenbuf.hline(cx, by, cw, curses.ACS_HLINE, color)
            STDSCR.hline(by, cx, curses.ACS_HLINE, cw)

        # top left corner
        if self.rect.clip_point(x, y):
            self.screenbuf[x, y] = (curses.ACS_ULCORNER, color)
            STDSCR.addch(y, x, curses.ACS_ULCORNER)

        # bottom left corner
        if self.rect.clip_point(x, by):
            self.screenbuf[x, by] = (curses.ACS_LLCORNER, color)
            STDSCR.addch(by, x, curses.ACS_LLCORNER)

        # top right corner
        if self.rect.clip_point(rx, y):
            self.screenbuf[rx, y] = (curses.ACS_URCORNER, color)
            STDSCR.addch(y, rx, curses.ACS_URCORNER)

        # bottom right corner
        if self.rect.clip_point(rx, by):
            self.screenbuf[rx, by] = (curses.ACS_LRCORNER, color)
            STDSCR.addch(by, rx, curses.ACS_LRCORNER)

        STDSCR.attrset(self.curses_color)

    def color_hline(self, x, y, w, color=-1):
        '''draw horizontal color line'''

        visible, x, y, w = self.rect.clip_hline(x, y, w)
        if not visible:
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

        visible, x, y, h = self.rect.clip_vline(x, y, h)
        if not visible:
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

    def getrect(self, x, y, w, h):
        '''Returns ScreenBuf object with copy of x,y,w,h
        or None if outside clip area
        '''

        visible, x, y, w, h = self.rect.clip_rect(x, y, w, h)
        if not visible:
            return None

        copy = ScreenBuf(w, h)
        copy.copyrect(0, 0, self.screenbuf, x, y, w, h)
        return copy

    def putrect(self, x, y, buf):
        '''Put ScreenBuf buf at x, y'''

        if buf is None:
            return

        visible, x, y, w, h = self.rect.clip_rect(x, y, buf.w, buf.h)
        if not visible:
            return

        self.screenbuf.copyrect(x, y, buf, 0, 0, buf.w, buf.h)
        # update the curses screen
        prev_color = None
        offset = self.w * y + x
        for j in xrange(0, h):
            for i in xrange(0, w):
                ch, color = self.screenbuf[offset]
                if isinstance(ch, str):
                    ch = ord(ch)

                if color != prev_color:
                    # only reset attr when the color did change
                    prev_color = color
                    attr = curses_color(color)

                offset += 1
                STDSCR.addch(y + j, x + i, ch, attr)
            offset += self.w - w



class ColorSet(object):
    '''collection of colors'''

    def __init__(self, fg=WHITE, bg=BLACK, bold=False):
        '''initialize'''

        self.text = video_color(fg, bg, bold)
        self.border = self.text
        self.title = self.text
        self.cursor = reverse_video(self.text)
        self.status = self.text
        self.scrollbar = self.text
        self.shadow = video_color(BLACK, BLACK, True)

        # not all views use these, but set them anyway
        self.button = self.text
        self.buttonhotkey = self.text
        self.activebutton = self.text
        self.activebuttonhotkey = self.text

        self.menu = self.text
        self.menuhotkey = self.text
        self.activemenu = self.text
        self.activemenuhotkey = self.text



class Window(object):
    '''represents a window'''

    OPEN = 1
    SHOWN = 2
    FOCUS = 4

    def __init__(self, x, y, w, h, colors, title=None, border=True):
        '''initialize'''

        self.frame = Rect(x, y, w, h)
        self.colors = colors
        self.title = title
        self.has_border = border

        # bounds is the inner area; for view content
        self.bounds = Rect(x + 1, y + 1, w - 2, h - 2)

        # rect is the outer area; larger because of shadow
        self.rect = Rect(x, y, w + 2, h + 1)
        self.back = None
        self.flags = 0

    def save_background(self):
        '''save the background'''

        self.back = VIDEO.getrect(self.rect.x, self.rect.y,
                                  self.rect.w, self.rect.h)

    def restore_background(self):
        '''restore the background'''

        VIDEO.putrect(self.rect.x, self.rect.y, self.back)

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

    def lose_focus(self):
        '''event: focus lost'''

        self.flags &= ~Window.FOCUS
        self.draw_cursor()

    def draw(self):
        '''draw the window'''

        if not self.flags & Window.SHOWN:
            return

        # draw rect
        VIDEO.fillrect(self.frame.x, self.frame.y, self.frame.w, self.frame.h,
                       self.colors.text)
        # draw border
        if self.has_border:
            VIDEO.border(self.frame.x, self.frame.y, self.frame.w,
                         self.frame.h, self.colors.border)

        # draw frame shadow
        self.draw_shadow()

        # draw title
        if self.title is not None:
            title = ' ' + self.title + ' '
            x = (self.frame.w - len(title)) / 2
            VIDEO.puts(self.frame.x + x, self.frame.y, title,
                       self.colors.title)

    def draw_shadow(self):
        '''draw shadow for frame rect'''

        if not self.flags & Window.SHOWN:
            return

        # right side shadow vlines
        VIDEO.color_vline(self.frame.x + self.frame.w, self.frame.y + 1,
                          self.frame.h, self.colors.shadow)
        VIDEO.color_vline(self.frame.x + self.frame.w + 1, self.frame.y + 1,
                          self.frame.h, self.colors.shadow)
        # bottom shadow hline
        VIDEO.color_hline(self.frame.x + 2, self.frame.y + self.frame.h,
                          self.frame.w, self.colors.shadow)

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
            color = self.colors.text

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
            color = self.colors.text

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

    def __init__(self, x, y, w, h, colors, title=None, border=True,
                 text=None, tabsize=4):
        '''initialize'''

        super(TextWindow, self).__init__(x, y, w, h, colors, title, border)
        if text is None:
            self.text = []
        else:
            self.text = text
        self.tabsize = tabsize

        self.top = 0
        self.cursor = 0
        self.xoffset = 0
        self.scrollbar_y = 0
        self.scrollbar_h = 0
        self.status = ''

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
        self.draw_statusbar()

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

        if self.flags & Window.FOCUS:
            color = self.colors.cursor
        else:
            color = -1
        self.printline(self.cursor, color)

        self.update_statusbar(' %d,%d ' % (self.top + self.cursor + 1,
                                           self.xoffset + 1))

    def clear_cursor(self):
        '''erase the cursor'''

        self.printline(self.cursor)

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
                    self.scrollbar_h, curses.ACS_VLINE, self.colors.border)

    def draw_scrollbar(self):
        '''draw scrollbar'''

        if not self.has_border or self.scrollbar_h <= 0:
            return

        y = self.scrollbar_y - self.scrollbar_h / 2
        if y < 0:
            y = 0
        if y > self.bounds.h - self.scrollbar_h:
            y = self.bounds.h - self.scrollbar_h

        VIDEO.vline(self.frame.x + self.frame.w - 1, self.bounds.y + y,
                    self.scrollbar_h, curses.ACS_CKBOARD,
                    self.colors.scrollbar)

    def update_statusbar(self, msg):
        '''update the statusbar'''

        if msg == self.status:
            return

        if len(msg) < len(self.status):
            # clear the statusbar
            w = len(self.status) - len(msg)
            x = self.bounds.w - 1 - len(self.status)
            if x < 0:
                x = 0
                w = self.bounds.w
            VIDEO.hline(self.bounds.x + x, self.frame.y + self.frame.h - 1, w,
                        curses.ACS_HLINE, self.colors.border)

        self.status = msg
        self.draw_statusbar()

    def draw_statusbar(self):
        '''draw statusbar'''

        x = self.bounds.w - 1 - len(self.status)
        if x < 0:
            x = 0

        msg = self.status
        if len(msg) > self.bounds.w:
            msg = msg[self.bounds.w:]

        VIDEO.puts(self.bounds.x + x, self.bounds.y + self.bounds.h, msg,
                   self.colors.status)

    def move_up(self):
        '''move up'''

        if self.cursor > 0:
            self.clear_cursor()
            self.cursor -= 1
        else:
            self.scroll_up()

        self.update_scrollbar()
        self.draw_cursor()

    def move_down(self):
        '''move down'''

        if not self.text or self.cursor >= len(self.text) - 1:
            return

        if self.cursor < self.bounds.h - 1:
            self.clear_cursor()
            self.cursor += 1
        else:
            self.scroll_down()

        self.update_scrollbar()
        self.draw_cursor()

    def move_left(self):
        '''move left'''

        if self.xoffset > 0:
            self.xoffset -= 4
            if self.xoffset < 0:
                self.xoffset = 0
            self.draw_text()
        self.draw_cursor()

    def move_right(self):
        '''move right'''

        max_xoffset = 500
        if self.xoffset < max_xoffset:
            self.xoffset += 4
            self.draw_text()
        self.draw_cursor()

    def scroll_up(self):
        '''scroll up one line'''

        old_top = self.top
        self.top -= 1
        if self.top < 0:
            self.top = 0

        if self.top != old_top:
            self.draw_text()

    def scroll_down(self):
        '''scroll down one line'''

        old_top = self.top
        self.top += 1
        if self.top > len(self.text) - self.bounds.h:
            self.top = len(self.text) - self.bounds.h
            if self.top < 0:
                self.top = 0

        if self.top != old_top:
            self.draw_text()

    def pageup(self):
        '''scroll one page up'''

        old_top = self.top
        old_cursor = new_cursor = self.cursor

        if old_cursor == self.bounds.h - 1:
            new_cursor = 0
        else:
            self.top -= self.bounds.h - 1
            if self.top < 0:
                self.top = 0
                new_cursor = 0

        if self.top != old_top:
            self.cursor = new_cursor
            self.draw_text()
        elif old_cursor != new_cursor:
            self.clear_cursor()
            self.cursor = new_cursor

        self.update_scrollbar()
        self.draw_cursor()

    def pagedown(self):
        '''scroll one page down'''

        old_top = self.top
        old_cursor = new_cursor = self.cursor

        if old_cursor == 0:
            new_cursor = self.bounds.h - 1
        else:
            self.top += self.bounds.h - 1
            if self.top > len(self.text) - self.bounds.h:
                self.top = len(self.text) - self.bounds.h
                if self.top < 0:
                    self.top = 0
                new_cursor = self.bounds.h - 1
                if new_cursor >= len(self.text):
                    new_cursor = len(self.text) - 1
                    if new_cursor < 0:
                        new_cursor = 0

        if self.top != old_top:
            self.cursor = new_cursor
            self.draw_text()
        elif old_cursor != new_cursor:
            self.clear_cursor()
            self.cursor = new_cursor

        self.update_scrollbar()
        self.draw_cursor()

    def goto_top(self):
        '''go to top of document'''

        old_top = self.top
        old_cursor = new_cursor = self.cursor
        old_xoffset = self.xoffset

        self.top = self.xoffset = new_cursor = 0
        if old_top != self.top or old_xoffset != self.xoffset:
            self.cursor = new_cursor
            self.draw_text()
        elif old_cursor != new_cursor:
            self.clear_cursor()
            self.cursor = new_cursor

        self.update_scrollbar()
        self.draw_cursor()

    def goto_bottom(self):
        '''go to bottom of document'''

        old_top = self.top
        old_cursor = new_cursor = self.cursor
        old_xoffset = self.xoffset

        self.top = len(self.text) - self.bounds.h
        if self.top < 0:
            self.top = 0

        new_cursor = self.bounds.h - 1
        if new_cursor >= len(self.text):
            new_cursor = len(self.text) - 1
            if new_cursor < 0:
                new_cursor = 0

        self.xoffset = 0

        if self.top != old_top or old_xoffset != self.xoffset:
            self.cursor = new_cursor
            self.draw_text()
        elif old_cursor != new_cursor:
            self.clear_cursor()
            self.cursor = new_cursor

        self.update_scrollbar()
        self.draw_cursor()

    def runloop(self):
        '''run main input loop for this view
        Returns a new program state code
        '''

        while True:
            key = getch()

            if key == KEY_ESC:
                self.lose_focus()
                break

            elif key == KEY_UP:
                self.move_up()

            elif key == KEY_DOWN:
                self.move_down()

            elif key == KEY_LEFT:
                self.move_left()

            elif key == KEY_RIGHT:
                self.move_right()

            elif key == KEY_PAGEUP:
                self.pageup()

            elif key == KEY_PAGEDOWN:
                self.pagedown()

            elif key == KEY_HOME:
                self.goto_top()

            elif key == KEY_END:
                self.goto_bottom()



class Widget(object):
    '''represents a widget'''

    def __init__(self, parent, x, y, colors):
        '''initialize'''

        self.parent = parent
        self.x = x
        self.y = y
        self.colors = colors
        self.has_focus = False

    def draw(self):
        '''draw widget'''

        # override this method
        pass

    def gain_focus(self):
        '''we get focus'''

        self.has_focus = True
        self.draw_cursor()

    def lose_focus(self):
        '''we lose focus'''

        self.has_focus = False
        self.draw_cursor()

    def draw_cursor(self):
        '''draw cursor'''

        # override this method
        pass



class Button(Widget):
    '''represents a button'''

    def __init__(self, parent, x, y, colors, label):
        '''initialize'''

        assert label is not None

        super(Button, self).__init__(parent, x, y, colors)

        self.hotkey, self.hotkey_pos, self.label = label_hotkey(label)

        self.pushing = False

    def draw(self):
        '''draw button'''

        self.draw_cursor()

    def draw_cursor(self):
        '''draw button'''

        # the cursor _is_ the button
        # and the button is the cursor

        add = 1
        text = ' ' + self.label + ' '
        if len(text) <= 5:
            # minimum width is 7
            text = ' ' + text + ' '
            add += 1

        if self.has_focus:
            text = '>' + text + '<'
            color = self.colors.activebutton
        else:
            text = ' ' + text + ' '
            color = self.colors.button
        add += 1

        xpos = self.x
        if self.pushing:
            xpos += 1

        self.parent.puts(xpos, self.y, text, color)

        if self.hotkey_pos > -1:
            # draw hotkey
            if self.has_focus:
                color = self.colors.activebuttonhotkey
            else:
                color = self.colors.buttonhotkey

            self.parent.puts(xpos + self.hotkey_pos + add, self.y,
                             self.hotkey, color)

    def push(self):
        '''push the button'''

        assert self.has_focus

        # animate button
        self.pushing = True
        self.parent.draw()
        STDSCR.refresh()
        curses.doupdate()
        time.sleep(0.1)

        self.pushing = False
        self.parent.draw()
        STDSCR.refresh()
        curses.doupdate()
        time.sleep(0.1)



class Alert(Window):
    '''an alert box with buttons'''

    def __init__(self, colors, title, msg, buttons=None, default=0,
                 border=True):
        '''initialize'''

        # determine width and height
        w = 0
        lines = msg.split('\n')
        for line in lines:
            if len(line) > w:
                w = len(line)
        w += 2
        if buttons is not None:
            bw = 0
            for label in buttons:
                bw += button_width(label) + 2
            bw += 2
            if bw > w:
                w = bw

        h = len(lines) + 5
        if border:
            w += 2
            h += 2

        # center the box
        x = center_x(w)
        y = center_y(h)

        super(Alert, self).__init__(x, y, w, h, colors, title, border)

        self.text = lines

        # y position of the button bar
        y = self.bounds.h - 2
        assert y > 0

        self.hotkeys = []

        if buttons is None:
            # one OK button: center it
            label = '<O>K'
            x = center_x(button_width(label), self.bounds.w)
            self.buttons = [Button(self, x, y, self.colors, label),]
        else:
            # make and position button widgets
            self.buttons = []

            # determine spacing
            total_len = 0
            for label in buttons:
                total_len += button_width(label)

            # spacing is a floating point number
            # but the button will have an integer position
            spacing = (self.bounds.w - total_len) / (len(buttons) + 1.0)
            if spacing < 1.0:
                spacing = 1.0

            x = spacing
            for label in buttons:
                button = Button(self, int(x), y, self.colors, label)
                self.buttons.append(button)
                x += spacing + button_width(label)

                # save hotkey
                hotkey, _, _ = label_hotkey(label)
                self.hotkeys.append(hotkey)

        assert default >= 0 and default < len(self.buttons)
        self.cursor = self.default = default

    def draw(self):
        '''draw the alert box'''

        super(Alert, self).draw()

        # draw the text
        y = 1
        for line in self.text:
            x = (self.bounds.w - len(line)) / 2
            self.cputs(x, y, line)
            y += 1

        # draw buttons
        self.draw_buttons()

    def draw_buttons(self):
        '''draw the buttons'''

        for button in self.buttons:
            button.draw()

    def move_right(self):
        '''select button to the right'''

        if len(self.buttons) <= 1:
            return

        self.buttons[self.cursor].lose_focus()
        self.cursor += 1
        if self.cursor >= len(self.buttons):
            self.cursor = 0
        self.buttons[self.cursor].gain_focus()

    def move_left(self):
        '''select button to the left'''

        if len(self.buttons) <= 1:
            return

        self.buttons[self.cursor].lose_focus()
        self.cursor -= 1
        if self.cursor < 0:
            self.cursor = len(self.buttons) - 1
        self.buttons[self.cursor].gain_focus()

    def push(self):
        '''push selected button'''

        self.buttons[self.cursor].push()

    def push_hotkey(self, key):
        '''push hotkey
        Returns True if key indeed pushed a button
        '''

        if not self.hotkeys:
            return

        if len(key) == 1:
            key = key.upper()

        idx = 0
        for hotkey in self.hotkeys:
            if hotkey == key:
                if self.cursor != idx:
                    self.buttons[self.cursor].lose_focus()
                    self.cursor = idx
                    self.buttons[self.cursor].gain_focus()

                self.push()
                return True

            idx += 1

        return False

    def runloop(self):
        '''run the alert dialog
        Returns button choice or -1 on escape
        '''

        # always open with the default button active
        self.cursor = self.default
        self.buttons[self.cursor].gain_focus()

        while True:
            key = getch()

            if key == KEY_ESC:
                self.close()
                return -1

            elif key == KEY_LEFT or key == KEY_BTAB:
                self.move_left()

            elif key == KEY_RIGHT or key == KEY_TAB:
                self.move_right()

            elif key == KEY_RETURN or key == ' ':
                self.push()
                self.close()
                return self.cursor

            elif self.push_hotkey(key):
                self.close()
                return self.cursor



def video_color(fg, bg=None, bold=False):
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


def reverse_video(color):
    '''Returns reverse of combined color code'''

    bg = color >> 4
    fg = color & 7
    # in general looks nicer without bold
#    bold = color & BOLD
    return (fg << 4) | bg


def curses_color(fg, bg=None, bold=False):
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


def label_hotkey(label):
    '''Returns triple: (hotkey, hotkey position, plaintext) of the label
    or None if there is none

    Mind that hotkeys are uppercase, or may also be "Ctrl-key"
    '''

    m = REGEX_HOTKEY.match(label)
    if m is None:
        return (None, -1, label)

    hotkey = m.groups()[0]
    if len(hotkey) == 1:
        hotkey = hotkey.upper()

    hotkey_pos = label.find('<')
    if hotkey_pos > -1:
        # strip out hooks
        plaintext = label.replace('<', '').replace('>', '')
    else:
        plaintext = label

    return (hotkey, hotkey_pos, plaintext)


def label_length(label):
    '''Returns visual label length'''

    m = REGEX_HOTKEY.match(label)
    if m is None:
        return len(label)
    else:
        return len(label) - 2


def button_width(label):
    '''Returns visual size of a button'''

    if isinstance(label, Button):
        label = label.label

    assert isinstance(label, str)

    w = label_length(label)
    if w <= 3:
        w += 2
    return w + 4


def center_x(width, area=0):
    '''Return centered x coordinate
    If area is not given, center on screen
    '''

    if area == 0:
        area = VIDEO.w

    x = (area - width) * 0.5

    # round up for funny looking non-centered objects
    return int(x + 0.5)


def center_y(height, area=0):
    '''Return centered y coordinate
    If area is not given, put it in top half of screen
    '''

    if area == 0:
        y = (VIDEO.h - height) * 0.35
    else:
        y = (area - height) * 0.5

    return int(y + 0.5)


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

    bgcolors = ColorSet(YELLOW, RED, True)
    bgwin = Window(15, 20, 50, 16, bgcolors, title='Back')
    bgwin.show()
    bgwin.puts(0, 0, 'This is the back window')

    getch()

    wincolors = ColorSet(WHITE, BLUE, True)
    wincolors.border = video_color(CYAN, BLUE, True)
    wincolors.title = video_color(YELLOW, BLUE, True)
    wincolors.cursor = video_color(WHITE, BLACK, True)
    wincolors.status = video_color(BLACK, WHITE, False)
    wincolors.scrollbar = wincolors.border

    win = TextWindow(10, 10, 50, 20, wincolors, title='Hello')
    win.load('textmode.py')
    win.show()

    pinky = VIDEO.set_color(YELLOW, MAGENTA)
    VIDEO.set_color(YELLOW, GREEN)

    x = VIDEO.w / 2 - 1
    y = VIDEO.h / 2

    VIDEO.putch(x, y, 'W')
    VIDEO.putch(x + 1, y, 'J', pinky)

    alert_colors = ColorSet(BLACK, WHITE)
    alert_colors.title = video_color(RED, WHITE)
    alert_colors.button = video_color(WHITE, BLUE, bold=True)
    alert_colors.buttonhotkey = video_color(YELLOW, BLUE, bold=True)
    alert_colors.activebutton = video_color(WHITE, GREEN, bold=True)
    alert_colors.activebuttonhotkey = video_color(YELLOW, GREEN, bold=True)

    alert = Alert(alert_colors, title='Alert', msg='Failed to load file',
                  buttons=['<C>ancel', '<O>K'], default=1)
    alert.show()
    choice = alert.runloop()
    debug('choice == %d' % choice)

    win.runloop()

    win.close()
    bgwin.cputs(0, 0, 'Bye!')

    getch()

    terminate()



if __name__ == '__main__':
    unit_test()


# EOB

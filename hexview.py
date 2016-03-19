#! /usr/bin/env python
#
#   hexview.py  WJ116
#
#   Copyright 2016 by Walter de Jong <walter@heiho.net>
#

'''hex file viewer'''

import curses

import textmode

from textmode import Rect
from textmode import WHITE, YELLOW, GREEN, CYAN, BLUE, MAGENTA, RED, BLACK
from textmode import getch, KEY_ESC, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT
from textmode import KEY_PAGEUP, KEY_PAGEDOWN, KEY_HOME, KEY_END, KEY_RETURN
from textmode import KEY_TAB, KEY_BTAB, KEY_BS, KEY_DEL
from textmode import debug

VERSION = '0.9-beta'


class MemoryFile(object):
    '''access file data as if it is an in-memory array'''

    IOSIZE = 256 * 1024

    def __init__(self, filename=None, pagesize=25*16):
        '''initialise'''

        self.filename = None
        self.filesize = 0
        self.fd = None
        self.low = self.high = 0
        self.pagesize = pagesize
        self.cachesize = self.pagesize * 3
        # round up to nearest multiple of
        if self.cachesize % MemoryFile.IOSIZE != 0:
            self.cachesize += (MemoryFile.IOSIZE -
                               (self.cachesize % MemoryFile.IOSIZE))
        self.data = None

        if filename is not None:
            self.load(filename)

    def load(self, filename):
        '''open file'''

        self.filename = filename
        self.filesize = os.path.getsize(self.filename)
        self.fd = open(filename)
        self.data = bytearray(self.fd.read(self.cachesize))
        self.low = 0
        self.high = len(self.data)

    def close(self):
        '''close the file'''

        if self.fd is not None:
            self.fd.close()
            self.fd = None

        self.filename = None
        self.filesize = 0
        self.data = None

    def __len__(self):
        '''Returns length'''

        return self.filesize

    def __getitem__(self, idx):
        '''Return byte or range at idx'''

        if isinstance(idx, int):
            # return byte at address
            if idx < 0 or idx >= self.filesize:
                raise IndexError('MemoryFile out of bounds error')

            if idx < self.low or idx >= self.high:
                self.pagefault(idx)

            return self.data[idx - self.low]

        elif isinstance(idx, slice):
            # return slice
            if idx.start < 0 or idx.stop > self.filesize:
                raise IndexError('MemoryFile out of bounds error')

            if idx.start < self.low or idx.stop > self.high:
                self.pagefault(self.low)

            return self.data[idx.start - self.low:
                             idx.stop - self.low:idx.step]

        else:
            raise TypeError('invalid argument type')

    def pagefault(self, addr):
        '''page in data as needed'''

        self.low = addr - self.cachesize / 2
        if self.low < 0:
            self.low = 0

        self.high = addr + self.cachesize / 2
        if self.high > self.filesize:
            self.high = self.filesize

        self.fd.seek(self.low, os.SEEK_SET)
        size = self.high - self.low
        self.data = bytearray(self.fd.read(size))
        self.high = self.low + len(self.data)

    def find(self, searchtext, pos):
        '''find searchtext
        Returns -1 if not found
        '''

        if pos < 0 or pos >= self.filesize:
            return -1

        if pos < self.low or pos + len(searchtext) >= self.high:
            self.pagefault(self.low)

        pos -= self.low

        while True:
            idx = self.data.find(searchtext, pos)
            if idx >= 0:
                # found
                return idx + self.low

            if self.high >= self.filesize:
                # not found
                return -1

            self.low = self.high - len(searchtext)
            self.pagefault(self.low)



class HexWindow(textmode.Window):
    '''hex viewer main window'''

    OPT_8_BIT = 1
    OPT_16_BIT = 2
    OPT_16_BIT_SWAP = 3
    OPT_32_BIT = 4
    OPT_32_BIT_SWAP = 5

    MODE_SELECT = 1

    # search direction
    FORWARD = 0
    BACKWARD = 1

    def __init__(self, x, y, w, h, colors, title=None, border=True):
        '''initialize'''

        super(HexWindow, self).__init__(x, y, w, h, colors, title, border)

        # turn off window shadow for HexWindow
        # because it clobbers the bottom statusbar
        self.has_shadow = False

        self.data = None
        self.address = 0
        self.cursor_x = self.cursor_y = 0
        self.view_option = HexWindow.OPT_8_BIT
        self.mode = 0
        self.selection_start = self.selection_end = 0
        self.old_addr = self.old_x = self.old_y = 0

        colors = textmode.ColorSet(WHITE, BLACK)
        colors.cursor = textmode.video_color(WHITE, GREEN, bold=True)
        self.cmdline = CommandBar(colors, prompt=':')
        self.search = CommandBar(colors, prompt='/')
        self.searchdir = HexWindow.FORWARD
        self.hexsearch = CommandBar(colors, prompt='x/',
                                    inputfilter=hex_inputfilter)
        self.jumpaddr = CommandBar(colors, prompt='@',
                                   inputfilter=hex_inputfilter)
        self.addaddr = CommandBar(colors, prompt='@+',
                                  inputfilter=hex_inputfilter)

        # this is a hack; I always want a visible cursor
        # even though the command bar can be the front window
        # so we can ignore focus events sometimes
        self.ignore_focus = False

    def resize_event(self):
        '''the terminal was resized'''

        # always keep same width, but height may vary
        x = self.frame.x
        y = self.frame.y
        w = self.frame.w
        h = self.frame.h = textmode.VIDEO.h - 1

        # bounds is the inner area; for view content
        if self.has_border:
            self.bounds = Rect(x + 1, y + 1, w - 2, h - 2)
        else:
            self.bounds = self.frame

        # rect is the outer area; larger because of shadow
        self.rect = Rect(x, y, w + 2, h + 1)

        if self.cursor_y >= self.bounds.h:
            self.cursor_y = self.bounds.h - 1

        # resize the command and search bars
        self.cmdline.resize_event()
        self.search.resize_event()
        self.hexsearch.resize_event()
        self.jumpaddr.resize_event()
        self.addaddr.resize_event()

    def load(self, filename):
        '''load file
        Raises IOError on error
        '''

        self.data = MemoryFile(filename, self.bounds.h * 16)

        self.title = os.path.basename(filename)
        if len(self.title) > self.bounds.w:
            self.title = self.title[:self.bounds.w - 6] + '...'

    def close(self):
        '''close window'''

        self.data.close()

        super(HexWindow, self).close()

    def lose_focus(self):
        '''we lose focus'''

        if self.ignore_focus:
            # ignore only once
            self.ignore_focus = False
            return

        super(HexWindow, self).lose_focus()

    def draw(self):
        '''draw the window'''

        if not self.flags & textmode.Window.SHOWN:
            return

        super(HexWindow, self).draw()

        if self.view_option == HexWindow.OPT_8_BIT:
            self.draw_view_8bit()

        elif self.view_option == HexWindow.OPT_16_BIT:
            self.draw_view_16bit()

        elif self.view_option == HexWindow.OPT_16_BIT_SWAP:
            self.draw_view_16bit_swapped()

        elif self.view_option == HexWindow.OPT_32_BIT:
            self.draw_view_32bit()

        elif self.view_option == HexWindow.OPT_32_BIT_SWAP:
            self.draw_view_32bit_swapped()

        self.draw_statusbar()
        # FIXME draw selection (in draw_cursor() ?)

    def draw_statusbar(self):
        '''draw statusbar'''

        status = None
        if self.mode & HexWindow.MODE_SELECT:
            status = 'Select'

        if status is None:
            textmode.VIDEO.hline(self.bounds.x + self.bounds.w - 12,
                        self.bounds.y + self.bounds.h, 10, curses.ACS_HLINE,
                        self.colors.border)
        else:
            textmode.VIDEO.puts(self.bounds.x + self.bounds.w - 2 - len(status),
                       self.bounds.y + self.bounds.h, status,
                       self.colors.status)

    def draw_view_8bit(self):
        '''draw hexview for single bytes'''

        y = 0
        while y < self.bounds.h:
            # address
            offset = self.address + y * 16
            line = '%08X  ' % offset

            # bytes (left block)
            try:
                # try fast(er) implementation
                line += (('%02X %02X %02X %02X %02X %02X %02X %02X  '
                          '%02X %02X %02X %02X %02X %02X %02X %02X') %
                          (self.data[offset], self.data[offset + 1],
                           self.data[offset + 2], self.data[offset + 3],
                           self.data[offset + 4], self.data[offset + 5],
                           self.data[offset + 6], self.data[offset + 7],
                           self.data[offset + 8], self.data[offset + 9],
                           self.data[offset + 10], self.data[offset + 11],
                           self.data[offset + 12], self.data[offset + 13],
                           self.data[offset + 14], self.data[offset + 15]))
            except IndexError:
                # do the slower version
                for i in xrange(0, 8):
                    try:
                        line += '%02X ' % self.data[offset + i]
                    except IndexError:
                        line += '   '
                line += ' '
                for i in xrange(8, 16):
                    try:
                        line += '%02X ' % self.data[offset + i]
                    except IndexError:
                        line += '   '

            self.puts(0, y, line, self.colors.text)

            self.draw_ascii(y)
            y += 1

    def draw_view_16bit(self):
        '''draw hexview for 16 bit words'''

        y = 0
        while y < self.bounds.h:
            # address
            offset = self.address + y * 16
            line = '%08X  ' % offset

            # left block
            try:
                # try fast(er) implementation
                line += (('%02X%02X  %02X%02X  %02X%02X  %02X%02X   '
                          '%02X%02X  %02X%02X  %02X%02X  %02X%02X') %
                          (self.data[offset], self.data[offset + 1],
                           self.data[offset + 2], self.data[offset + 3],
                           self.data[offset + 4], self.data[offset + 5],
                           self.data[offset + 6], self.data[offset + 7],
                           self.data[offset + 8], self.data[offset + 9],
                           self.data[offset + 10], self.data[offset + 11],
                           self.data[offset + 12], self.data[offset + 13],
                           self.data[offset + 14], self.data[offset + 15]))
            except IndexError:
                # do the slower version
                for i in xrange(0, 4):
                    try:
                        line += '%02X' % self.data[offset + i * 2]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 2 + 1]
                    except IndexError:
                        line += '  '
                    line += '  '

                offset += 8
                line += ' '
                # right block
                for i in xrange(0, 4):
                    try:
                        line += '%02X' % self.data[offset + i * 2]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 2 + 1]
                    except IndexError:
                        line += '  '
                    line += '  '

            self.puts(0, y, line, self.colors.text)

            self.draw_ascii(y)
            y += 1

    def draw_view_16bit_swapped(self):
        '''draw hexview for 16 bit words, swapped'''

        y = 0
        while y < self.bounds.h:
            # address
            offset = self.address + y * 16
            line = '%08X  ' % offset

            # left block
            try:
                # try fast(er) implementation
                line += (('%02X%02X  %02X%02X  %02X%02X  %02X%02X   '
                          '%02X%02X  %02X%02X  %02X%02X  %02X%02X') %
                          (self.data[offset + 1], self.data[offset],
                           self.data[offset + 3], self.data[offset + 2],
                           self.data[offset + 5], self.data[offset + 4],
                           self.data[offset + 7], self.data[offset + 6],
                           self.data[offset + 9], self.data[offset + 8],
                           self.data[offset + 11], self.data[offset + 10],
                           self.data[offset + 13], self.data[offset + 12],
                           self.data[offset + 15], self.data[offset + 14]))
            except IndexError:
                # do the slower version
                for i in xrange(0, 4):
                    try:
                        line += '%02X' % self.data[offset + i * 2 + 1]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 2]
                    except IndexError:
                        line += '  '
                    line += '  '

                offset += 8
                line += ' '
                # right block
                for i in xrange(0, 4):
                    try:
                        line += '%02X' % self.data[offset + i * 2 + 1]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 2]
                    except IndexError:
                        line += '  '
                    line += '  '

            self.puts(0, y, line, self.colors.text)

            self.draw_ascii(y)
            y += 1

    def draw_view_32bit(self):
        '''draw hexview for 32 bit words'''

        y = 0
        while y < self.bounds.h:
            # address
            offset = self.address + y * 16
            line = '%08X  ' % offset

            # left block
            try:
                # try fast(er) implementation
                line += (('%02X%02X%02X%02X    %02X%02X%02X%02X     '
                          '%02X%02X%02X%02X    %02X%02X%02X%02X') %
                          (self.data[offset], self.data[offset + 1],
                           self.data[offset + 2], self.data[offset + 3],
                           self.data[offset + 4], self.data[offset + 5],
                           self.data[offset + 6], self.data[offset + 7],
                           self.data[offset + 8], self.data[offset + 9],
                           self.data[offset + 10], self.data[offset + 11],
                           self.data[offset + 12], self.data[offset + 13],
                           self.data[offset + 14], self.data[offset + 15]))
            except IndexError:
                # do the slower version
                for i in xrange(0, 2):
                    try:
                        line += '%02X' % self.data[offset + i * 4]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 1]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 2]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 3]
                    except IndexError:
                        line += '  '
                    line += '    '

                offset += 8
                line += ' '
                # right block
                for i in xrange(0, 2):
                    try:
                        line += '%02X' % self.data[offset + i * 4]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 1]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 2]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 3]
                    except IndexError:
                        line += '  '
                    line += '    '

            self.puts(0, y, line, self.colors.text)

            self.draw_ascii(y)
            y += 1

    def draw_view_32bit_swapped(self):
        '''draw hexview for 32 bit words, swapped'''

        y = 0
        while y < self.bounds.h:
            # address
            offset = self.address + y * 16
            line = '%08X  ' % offset

            # left block
            try:
                # try fast(er) implementation
                line += (('%02X%02X%02X%02X    %02X%02X%02X%02X     '
                          '%02X%02X%02X%02X    %02X%02X%02X%02X') %
                          (self.data[offset + 1], self.data[offset],
                           self.data[offset + 3], self.data[offset + 2],
                           self.data[offset + 5], self.data[offset + 4],
                           self.data[offset + 7], self.data[offset + 6],
                           self.data[offset + 9], self.data[offset + 8],
                           self.data[offset + 11], self.data[offset + 10],
                           self.data[offset + 13], self.data[offset + 12],
                           self.data[offset + 15], self.data[offset + 14]))
            except IndexError:
                # do the slower version
                for i in xrange(0, 2):
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 3]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 2]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 1]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4]
                    except IndexError:
                        line += '  '
                    line += '    '

                offset += 8
                line += ' '
                # right block
                for i in xrange(0, 2):
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 3]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 2]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4 + 1]
                    except IndexError:
                        line += '  '
                    try:
                        line += '%02X' % self.data[offset + i * 4]
                    except IndexError:
                        line += '  '
                    line += '    '

            self.puts(0, y, line, self.colors.text)

            self.draw_ascii(y)
            y += 1

    def draw_ascii(self, y):
        '''draw ascii bytes for line y'''

        invis = []
        line = ''
        offset = self.address + y * 16
        for i in xrange(0, 16):
            try:
                ch = self.data[offset + i]
                if ch >= ord(' ') and ch <= ord('~'):
                    line += chr(ch)
                else:
                    line += '.'
                    invis.append(i)
            except IndexError:
                ch = ' '

        # put the ASCII bytes line
        self.puts(60, y, line, self.colors.text)

        # color invisibles
        for i in invis:
            self.color_putch(60 + i, y, self.colors.invisibles)

    def draw_cursor(self, clear=False, mark=None):
        '''draw cursor'''

        if not self.flags & textmode.Window.FOCUS:
            clear = True

        if clear:
            color = self.colors.text
        else:
            color = self.colors.cursor

        if mark is not None:
            color = mark

        if self.mode & HexWindow.MODE_SELECT:
            self.draw_selection()

        # position of hex view cursor depends on view_option
        if self.view_option == HexWindow.OPT_8_BIT:
            self.draw_cursor_8bit(color)

        elif self.view_option == HexWindow.OPT_16_BIT:
            self.draw_cursor_16bit(color)

        elif self.view_option == HexWindow.OPT_16_BIT_SWAP:
            self.draw_cursor_16bit_swap(color)

        elif self.view_option == HexWindow.OPT_32_BIT:
            self.draw_cursor_32bit(color)

        elif self.view_option == HexWindow.OPT_32_BIT_SWAP:
            self.draw_cursor_32bit_swap(color)

        y = self.cursor_y
        try:
            ch = self.data[self.address + y * 16 + self.cursor_x]
        except IndexError:
            # FIXME IndexError due to cursor movement should be prevented
            ch = ord(' ')
        self.draw_ascii_cursor(ch, color, clear)

    def draw_ascii_cursor(self, ch, color, clear):
        '''draw ascii cursor'''

        if clear:
            color = self.colors.text
        else:
            color = self.colors.cursor

        if ch >= ord(' ') and ch <= ord('~'):
            ch = chr(ch)
        else:
            ch = '.'
            if clear:
                color = self.colors.invisibles

        self.color_putch(60 + self.cursor_x, self.cursor_y, color)

    def draw_cursor_at(self, x, y, color):
        '''draw hex bytes cursor at x, y'''

        textmode.VIDEO.color_hline(self.bounds.x + x, self.bounds.y + y,
                                   2, color)

    def draw_cursor_8bit(self, color):
        '''draw hex bytes cursor'''

        x = 10 + self.cursor_x * 3
        if self.cursor_x >= 8:
            x += 1
        self.draw_cursor_at(x, self.cursor_y, color)

    def draw_cursor_16bit(self, color):
        '''draw hex bytes cursor'''

        x = 10
        x += self.cursor_x / 2 * 6
        if self.cursor_x & 1:
            x += 2
        if self.cursor_x >= 8:
            x += 1
        self.draw_cursor_at(x, self.cursor_y, color)

    def draw_cursor_16bit_swap(self, color):
        '''draw hex bytes cursor'''

        x = 10
        x += self.cursor_x / 2 * 6
        if not self.cursor_x & 1:
            x += 2
        if self.cursor_x >= 8:
            x += 1
        self.draw_cursor_at(x, self.cursor_y, color)

    def draw_cursor_32bit(self, color):
        '''draw hex bytes cursor'''

        x = 10
        x += self.cursor_x / 4 * 12
        mod = self.cursor_x % 4
        x += mod * 2
        if self.cursor_x >= 8:
            x += 1
        self.draw_cursor_at(x, self.cursor_y, color)

    def draw_cursor_32bit_swap(self, color):
        '''draw hex bytes cursor'''

        x = 10
        x += self.cursor_x / 4 * 12
        mod = self.cursor_x % 4
        x += (3 - mod) * 2
        if self.cursor_x >= 8:
            x += 1
        self.draw_cursor_at(x, self.cursor_y, color)

    def clear_cursor(self):
        '''clear the cursor'''

        self.draw_cursor(clear=True)

    def draw_selection(self):
        '''draw selection'''

        start = self.selection_start
        if start < self.address:
            start = self.address
        pagesize = self.bounds.h * 16
        end = self.selection_end
        if end > self.address + pagesize:
            end = self.address + pagesize

        startx = (start - self.address) % 16
        starty = (start - self.address) / 16
        endx = (end - self.address) % 16
        endy = (end - self.address) / 16

        if starty == endy:
            textmode.VIDEO.color_hline(self.bounds.x + 60 + startx,
                                       self.bounds.y + starty, endx - startx,
                                       self.colors.cursor)
        else:
            textmode.VIDEO.color_hline(self.bounds.x + 60 + startx,
                                       self.bounds.y + starty, 16 - startx,
                                       self.colors.cursor)
            for j in xrange(starty + 1, endy):
                textmode.VIDEO.color_hline(self.bounds.x + 60,
                                           self.bounds.y + j, 16,
                                           self.colors.cursor)
            textmode.VIDEO.color_hline(self.bounds.x + 60,
                                       self.bounds.y + endy, endx,
                                       self.colors.cursor)

    def scroll_up(self, nlines=1):
        '''scroll nlines up'''

        self.address -= nlines * 16
        if self.address < 0:
            self.address = 0

        self.draw()

    def scroll_down(self, nlines=1):
        '''scroll nlines down'''

        addr = self.address + nlines * 16

        pagesize = self.bounds.h * 16
        if addr > len(self.data) - pagesize:
            addr = len(self.data) - pagesize
        if addr < 0:
            addr = 0

        if addr != self.address:
            self.address = addr
            self.draw()

    def move_up(self):
        '''move cursor up'''

        if not self.cursor_y and not self.address:
            return

        self.clear_cursor()

        if not self.cursor_y:
            self.scroll_up()
        else:
            self.cursor_y -= 1

        self.update_selection()
        self.draw_cursor()

    def move_down(self):
        '''move cursor down'''

        if self.cursor_y >= self.bounds.h - 1:
            # scroll down
            addr = self.address
            self.scroll_down()
            if self.address == addr:
                # no change (already at end)
                return
        else:
            self.clear_cursor()
            self.cursor_y += 1

        self.update_selection()
        self.draw_cursor()

    def move_left(self):
        '''move cursor left'''

        if not self.cursor_x and not self.cursor_y:
            if not self.address:
                return

            self.scroll_up()
        else:
            self.clear_cursor()

        if not self.cursor_x:
            if self.cursor_y > 0:
                self.cursor_y -= 1
            self.cursor_x = 15
        else:
            self.cursor_x -= 1

        self.update_selection()
        self.draw_cursor()

    def move_right(self):
        '''move cursor right'''

        if self.cursor_x >= 15 and self.cursor_y >= self.bounds.h - 1:
            # scroll down
            addr = self.address
            self.scroll_down()
            if self.address == addr:
                # no change (already at end)
                return
        else:
            self.clear_cursor()

        if self.cursor_x >= 15:
            self.cursor_x = 0
            if self.cursor_y < self.bounds.h - 1:
                self.cursor_y += 1
        else:
            self.cursor_x += 1

        self.update_selection()
        self.draw_cursor()

    def roll_left(self):
        '''move left by one byte'''

        if not self.address:
            return

        self.address -= 1
        self.draw()
        self.draw_cursor()

    def roll_right(self):
        '''move right by one byte'''

        # FIXME this is not entirely correct
        # round up to nearest 16
        num = len(self.data)
        remainder = num % 16
        if remainder > 0:
            num += 16 - remainder

        top = num - self.bounds.h * 16
        if self.address < top:
            self.address += 1
            self.draw()
            self.draw_cursor()

    def pageup(self):
        '''page up'''

        if not self.address:
            if not self.cursor_y:
                return

            self.clear_cursor()
            self.cursor_y = 0
            self.update_selection()
            self.draw_cursor()
            return

        if self.cursor_y == self.bounds.h - 1:
            self.clear_cursor()
            self.cursor_y = 0
        else:
            self.scroll_up(self.bounds.h - 1)

        self.update_selection()
        self.draw_cursor()

    def pagedown(self):
        '''page down'''

        if self.cursor_y == 0:
            self.clear_cursor()
            self.cursor_y = self.bounds.h - 1
        else:
            addr = self.address
            self.scroll_down(self.bounds.h - 1)
            if self.address == addr:
                # no change
                if self.cursor_y >= self.bounds.h - 1:
                    return

                self.clear_cursor()
                self.cursor_y = self.bounds.h - 1

        self.update_selection()
        self.draw_cursor()

    def move_home(self):
        '''go to top of document'''

        if not self.address:
            if not self.cursor_x and not self.cursor_y:
                return

            self.clear_cursor()
        else:
            self.address = 0
            self.draw()

        self.cursor_x = self.cursor_y = 0
        self.update_selection()
        self.draw_cursor()

    def move_end(self):
        '''go to last page of document'''

        pagesize = self.bounds.h * 16
        top = len(self.data) - pagesize
        if top < 0:
            top = 0

        if self.address != top:
            self.address = top
            self.draw()
        else:
            self.clear_cursor()

        if len(self.data) < pagesize:
            self.cursor_y = len(self.data) / 16
            self.cursor_x = len(self.data) % 16
        else:
            self.cursor_y = self.bounds.h - 1
            self.cursor_x = 15

        self.update_selection()
        self.draw_cursor()

    def select_view(self, key):
        '''set view option'''

        update = False
        if key == '1' and self.view_option != HexWindow.OPT_8_BIT:
            self.view_option = HexWindow.OPT_8_BIT
            update = True

        elif key == '2' and self.view_option != HexWindow.OPT_16_BIT:
            self.view_option = HexWindow.OPT_16_BIT
            update = True

        elif key == '3' and self.view_option != HexWindow.OPT_16_BIT_SWAP:
            self.view_option = HexWindow.OPT_16_BIT_SWAP
            update = True

        elif key == '4' and self.view_option != HexWindow.OPT_32_BIT:
            self.view_option = HexWindow.OPT_32_BIT
            update = True

        elif key == '5' and self.view_option != HexWindow.OPT_32_BIT_SWAP:
            self.view_option = HexWindow.OPT_32_BIT_SWAP
            update = True

        if update:
            self.draw()
            self.draw_cursor()

    def mode_selection(self):
        '''toggle selection mode'''

        if not self.mode & HexWindow.MODE_SELECT:
            self.selection_start = (self.address + self.cursor_y * 16 +
                                    self.cursor_x)
            self.selection_end = self.selection_start

        self.mode ^= HexWindow.MODE_SELECT
        self.update_selection()

        if not self.mode & HexWindow.MODE_SELECT:
            # was not yet redrawn ... do it now
            self.draw()

        self.draw_cursor()

    def update_selection(self):
        '''update selection start/end'''

        if self.mode & HexWindow.MODE_SELECT:
            old_addr = self.old_addr + self.old_y * 16 + self.old_x
            addr = self.address + self.cursor_y * 16 + self.cursor_x

            if self.selection_start == self.selection_end:
                if addr < self.selection_start:
                    self.selection_start = addr
                elif addr > self.selection_end:
                    self.selection_end = addr
            else:
                if old_addr == self.selection_start:
                    self.selection_start = addr
                elif old_addr == self.selection_end:
                    self.selection_end = addr

            if self.selection_start > self.selection_end:
                # swap start, end
                # and PEP-8 looks amazingly stupid here
                (self.selection_start,
                 self.selection_end) = (self.selection_end,
                                        self.selection_start)

            self.draw()

    def search_error(self, msg):
        '''display error message for search functions'''

        self.ignore_focus = True
        self.search.show()
        self.search.cputs(0, 0, msg, textmode.video_color(WHITE, RED,
                                                          bold=True))
        getch()
        self.search.hide()

    def find(self, again=False):
        '''text search'''

        self.searchdir = HexWindow.FORWARD
        searchtext = ''

        if not again:
            self.search.prompt = '/'
            self.ignore_focus = True
            self.search.show()
            ret = self.search.runloop()
            if ret != textmode.ENTER:
                return

            searchtext = self.search.textfield.text
            if not searchtext:
                again = True

        if again:
            try:
                searchtext = self.search.textfield.history[-1]
            except IndexError:
                return

        if not searchtext:
            return

        pos = self.address + self.cursor_y * 16 + self.cursor_x
        if again:
            pos += 1

        try:
            offset = self.data.find(searchtext, pos)
        except ValueError:
            # not found
            offset = -1

        if offset == -1:
            self.search_error('Not found')
            return

        # text was found at offset
        self.clear_cursor()
        # if on the same page, move the cursor
        pagesize = self.bounds.h * 16
        if self.address < offset + len(searchtext) < self.address + pagesize:
            pass
        else:
            # scroll the page; change base address
            self.address = offset - self.bounds.h * 8
            if self.address > len(self.data) - pagesize:
                self.address = len(self.data) - pagesize
            if self.address < 0:
                self.address = 0

            self.draw()

        # move cursor location
        diff = offset - self.address
        self.cursor_y = diff / 16
        self.cursor_x = diff % 16
        self.draw_cursor()

    def find_backwards(self, again=False):
        '''text search backwards'''

        self.searchdir = HexWindow.BACKWARD
        searchtext = ''

        if not again:
            self.search.prompt = '?'
            self.ignore_focus = True
            self.search.show()
            ret = self.search.runloop()
            if ret != textmode.ENTER:
                return

            searchtext = self.search.textfield.text
            if not searchtext:
                again = True

        if again:
            try:
                searchtext = self.search.textfield.history[-1]
            except IndexError:
                return

        if not searchtext:
            return

        pos = self.address + self.cursor_y * 16 + self.cursor_x
        try:
            offset = bytearray_find_backwards(self.data, searchtext, pos)
        except ValueError:
            # not found
            offset = -1

        if offset == -1:
            self.search_error('Not found')
            return

        # text was found at offset
        self.clear_cursor()
        # if on the same page, move the cursor
        pagesize = self.bounds.h * 16
        if self.address < offset + len(searchtext) < self.address + pagesize:
            pass
        else:
            # scroll the page; change base address
            self.address = offset - self.bounds.h * 8
            if self.address > len(self.data) - pagesize:
                self.address = len(self.data) - pagesize
            if self.address < 0:
                self.address = 0

            self.draw()

        # move cursor location
        diff = offset - self.address
        self.cursor_y = diff / 16
        self.cursor_x = diff % 16
        self.draw_cursor()

    def find_hex(self, again=False):
        '''search hex string'''

        self.searchdir = HexWindow.FORWARD
        searchtext = ''

        if not again:
            self.ignore_focus = True
            self.hexsearch.show()
            ret = self.hexsearch.runloop()
            if ret != textmode.ENTER:
                return

            searchtext = self.hexsearch.textfield.text
            if not searchtext:
                again = True

        if again:
            try:
                searchtext = self.hexsearch.textfield.history[-1]
            except IndexError:
                return

        if not searchtext:
            return

        # convert ascii searchtext to raw byte string
        searchtext = searchtext.replace(' ', '')
        if not searchtext:
            return

        if len(searchtext) & 1:
            self.search_error('Invalid byte string (uneven number of digits)')
            return

        raw = ''
        for x in xrange(0, len(searchtext), 2):
            hex_string = searchtext[x:x + 2]
            try:
                value = int(hex_string, 16)
            except ValueError:
                self.search_error('Invalid value in byte string')
                return

            raw += chr(value)

        pos = self.address + self.cursor_y * 16 + self.cursor_x
        if again:
            pos += 1

        try:
            offset = self.data.find(raw, pos)
        except ValueError:
            # not found
            offset = -1

        if offset == -1:
            self.search_error('Not found')
            return

        # text was found at offset
        self.clear_cursor()
        # if on the same page, move the cursor
        pagesize = self.bounds.h * 16
        if self.address < offset + len(searchtext) < self.address + pagesize:
            pass
        else:
            # scroll the page; change base address
            self.address = offset - self.bounds.h * 8
            if self.address > len(self.data) - pagesize:
                self.address = len(self.data) - pagesize
            if self.address < 0:
                self.address = 0

            self.draw()

        # move cursor location
        diff = offset - self.address
        self.cursor_y = diff / 16
        self.cursor_x = diff % 16
        self.draw_cursor()

    def jump_address(self):
        '''jump to address'''

        self.ignore_focus = True
        self.jumpaddr.show()
        ret = self.jumpaddr.runloop()
        if ret != textmode.ENTER:
            return

        text = self.jumpaddr.textfield.text
        text = text.replace(' ', '')
        if not text:
            return

        try:
            addr = int(text, 16)
        except ValueError:
            self.search_error('Invalid address')
            return

        # make addr appear at cursor_y
        addr -= self.cursor_y * 16

        pagesize = self.bounds.h * 16
        if addr > len(self.data) - pagesize:
            addr = len(self.data) - pagesize
        if addr < 0:
            addr = 0

        if addr != self.address:
            self.address = addr
            self.draw()
            self.draw_cursor()

    def plus_offset(self):
        '''add offset'''

        self.addaddr.prompt = '@+'
        self.ignore_focus = True
        self.addaddr.show()
        ret = self.addaddr.runloop()
        if ret != textmode.ENTER:
            return

        text = self.addaddr.textfield.text
        text = text.replace(' ', '')
        if not text:
            return

        try:
            offset = int(text, 16)
        except ValueError:
            self.search_error('Invalid address')
            return

        addr = self.address + offset
        if addr < 0:
            self.search_error('Invalid address')
            return

        if addr > len(self.data):
            self.search_error('Invalid address')
            return

        pagesize = self.bounds.h * 16
        if addr > len(self.data) - pagesize:
            addr = len(self.data) - pagesize
        if addr < 0:
            addr = 0

        if addr == self.address:
            return

        self.address = addr
        self.draw()
        self.draw_cursor()

    def minus_offset(self):
        '''minus offset'''

        self.addaddr.prompt = '@-'
        self.ignore_focus = True
        self.addaddr.show()
        ret = self.addaddr.runloop()
        if ret != textmode.ENTER:
            return

        text = self.addaddr.textfield.text
        text = text.replace(' ', '')
        if not text:
            return

        try:
            offset = int(text, 16)
        except ValueError:
            self.search_error('Invalid address')
            return

        addr = self.address - offset
        if addr < 0:
            self.search_error('Invalid address')
            return

        if addr > len(self.data):
            self.search_error('Invalid address')
            return

        pagesize = self.bounds.h * 16
        if addr > len(self.data) - pagesize:
            addr = len(self.data) - pagesize
        if addr < 0:
            addr = 0

        if addr == self.address:
            return

        self.address = addr
        self.draw()
        self.draw_cursor()

    def copy_address(self):
        '''copy current address to jump history'''

        addr = self.address + self.cursor_y * 16 + self.cursor_x
        self.jumpaddr.textfield.history.append('%08X' % addr)

        # give visual feedback
        color = textmode.video_color(WHITE, RED, bold=True)
        self.draw_address(self.cursor_y, mark=color)
        self.draw_cursor(mark=color)

    def move_begin_line(self):
        '''goto beginning of line'''

        if self.cursor_x != 0:
            self.clear_cursor()
            self.cursor_x = 0
            self.draw_cursor()

    def move_end_line(self):
        '''goto end of line'''

        if self.cursor_x != 15:
            self.clear_cursor()
            self.cursor_x = 15
            self.draw_cursor()

    def move_top(self):
        '''goto top of screen'''

        if self.cursor_y != 0:
            self.clear_cursor()
            self.cursor_y = 0
            self.draw_cursor()

    def move_middle(self):
        '''goto middle of screen'''

        y = self.bounds.h / 2
        if self.cursor_y != y:
            self.clear_cursor()
            self.cursor_y = y
            self.draw_cursor()

    def move_bottom(self):
        '''goto bottom of screen'''

        if self.cursor_y != self.bounds.h - 1:
            self.clear_cursor()
            self.cursor_y = self.bounds.h - 1
            self.draw_cursor()

    def move_word(self):
        '''move to next word'''

        end = len(self.data) - 1
        addr = self.address + self.cursor_y * 16 + self.cursor_x

        if isalphanum(self.data[addr]):
            while isalphanum(self.data[addr]) and addr < end:
                addr += 1

        while isspace(self.data[addr]) and addr < end:
            addr += 1

        if addr == self.address:
            return

        pagesize = self.bounds.h * 16
        if self.address < addr < self.address + pagesize:
            # only move cursor
            self.clear_cursor()
            diff = addr - self.address
            self.cursor_y = diff / 16
            self.cursor_x = diff % 16
        else:
            # scroll page
            # round up to nearest 16
            addr2 = addr
            mod = addr2 % 16
            if mod != 0:
                addr2 += 16 - mod
            else:
                addr2 += 16
            self.address = addr2 - pagesize
            diff = addr - self.address
            self.cursor_y = diff / 16
            self.cursor_x = diff % 16
            self.draw()

        self.draw_cursor()

    def move_word_back(self):
        '''move to previous word'''

        addr = self.address + self.cursor_y * 16 + self.cursor_x

        # skip back over any spaces
        while addr > 0 and isspace(self.data[addr - 1]):
            addr -= 1

        # move to beginning of word
        while addr > 0 and isalphanum(self.data[addr - 1]):
            addr -= 1

        pagesize = self.bounds.h * 16
        if self.address < addr < self.address + pagesize:
            # only move cursor
            self.clear_cursor()
            diff = addr - self.address
            self.cursor_y = diff / 16
            self.cursor_x = diff % 16
        else:
            # scroll page
            # round up to nearest 16
            addr2 = addr
            mod = addr2 % 16
            if mod != 0:
                addr2 += 16 - mod
            else:
                addr2 += 16
            self.address = addr2 - pagesize
            if self.address < 0:
                self.address = 0
            diff = addr - self.address
            self.cursor_y = diff / 16
            self.cursor_x = diff % 16
            self.draw()

        self.draw_cursor()

    def command(self):
        '''command mode
        Returns 0 (do nothing) or app code
        '''

        self.ignore_focus = True
        self.cmdline.show()
        ret = self.cmdline.runloop()
        if ret != textmode.ENTER:
            return 0

        cmd = self.cmdline.textfield.text
        if not cmd:
            return 0

        elif cmd == 'help' or cmd == '?':
            self.show_help()

        elif cmd == 'about':
            self.show_about()

        elif cmd in ('q', 'q!', 'quit'):
            return textmode.QUIT

        elif cmd in ('wq', 'wq!', 'ZZ', 'exit'):
            return textmode.EXIT

        elif cmd == '0':
            self.move_home()

        else:
            self.ignore_focus = True
            self.cmdline.show()
            self.cmdline.cputs(0, 0, "Unknown command '%s'" % cmd,
                               textmode.video_color(WHITE, RED, bold=True))
            getch()
            self.cmdline.hide()

        return 0

    def show_help(self):
        '''show help window'''

        win = HelpWindow(self)
        win.show()
        win.runloop()
        win.close()

    def show_about(self):
        '''show About box'''

        win = AboutBox()
        win.show()
        win.runloop()

    def runloop(self):
        '''run the input loop
        Returns state change code
        '''

        self.gain_focus()
        while True:
            self.old_addr = self.address
            self.old_x = self.cursor_x
            self.old_y = self.cursor_y

            key = getch()

            if key == KEY_ESC:
                if self.mode & HexWindow.MODE_SELECT:
                    self.mode_selection()

            elif key == KEY_UP or key == 'k':
                self.move_up()

            elif key == KEY_DOWN or key == 'j':
                self.move_down()

            elif key == KEY_LEFT or key == 'h':
                self.move_left()

            elif key == KEY_RIGHT or key == 'l':
                self.move_right()

            elif key == '<' or key == ',':
                self.roll_left()

            elif key == '>' or key == '.':
                self.roll_right()

            elif key == KEY_PAGEUP or key == 'Ctrl-U':
                self.pageup()

            elif key == KEY_PAGEDOWN or key == 'Ctrl-V':
                self.pagedown()

            elif key == KEY_HOME or key == 'g':
                self.move_home()

            elif key == KEY_END or key == 'G':
                self.move_end()

            elif key in ('1', '2', '3', '4', '5'):
                self.select_view(key)

            elif key == 'v':
                self.mode_selection()

            elif key == ':':
                # command mode
                ret = self.command()
                if ret != 0:
                    return ret

            elif key == '?':
                # find backwards
                self.find_backwards()

            elif key == '/' or key == 'Ctrl-F':
                self.find()

            elif key == 'n' or key == 'Ctrl-G':
                # search again
                if self.searchdir == HexWindow.FORWARD:
                    self.find(again=True)
                elif self.searchdir == HexWindow.BACKWARD:
                    self.find_backwards(again=True)

            elif key == 'x' or key == 'Ctrl-X':
                self.find_hex()

            elif key == '0' or key == '^':
                self.move_begin_line()

            elif key == '$':
                self.move_end_line()

            elif key == 'H':
                self.move_top()

            elif key == 'M':
                self.move_middle()

            elif key == 'L':
                self.move_bottom()

            elif key == '@':
                self.jump_address()

            elif key == '+':
                self.plus_offset()

            elif key == '-':
                self.minus_offset()

            elif key == 'm':
                self.copy_address()

            elif key == 'w':
                self.move_word()

            elif key == 'b':
                self.move_word_back()



def bytearray_find_backwards(data, search, pos=-1):
    '''search bytearray backwards for string
    Returns index if found or -1 if not found
    May raise ValueError for invalid search
    '''

    if data is None or not len(data):
        raise ValueError

    if search is None or not search:
        raise ValueError

    if pos == -1:
        pos = len(data)

    if pos < 0:
        return ValueError

    pos -= len(search)
    while pos >= 0:
        if data[pos:pos + len(search)] == search:
            return pos

        pos -= 1

    return -1


def hex_inputfilter(key):
    '''hexadecimal input filter
    Returns character or None if invalid
    '''

    val = ord(key)
    if (val >= ord('0') and val <= ord('9') or
            val >= ord('a') and val <= ord('f') or
            val >= ord('A') and val <= ord('F') or
            val == ord(' ')):
        if val >= ord('a') and val <= ord('f'):
            key = key.upper()
        return key
    else:
        return None


def isalphanum(ch):
    '''Returns True if character is alphanumeric'''

    return ((ch >= ord('0') and ch <= ord('9')) or
            (ch >= ord('a') and ch <= ord('z')) or
            (ch >= ord('A') and ch <= ord('Z')) or
            (ch == ord('_')))


def isspace(ch):
    '''Returns True if character is treated as space'''

    return not isalphanum(ch)


class CommandBar(textmode.CmdLine):
    '''command bar
    Same as CmdLine, but backspace can exit the command mode
    '''

    def __init__(self, colors, prompt=None, inputfilter=None):
        '''initialize'''

        x = 0
        y = textmode.VIDEO.h - 1
        w = textmode.VIDEO.w
        super(CommandBar, self).__init__(x, y, w, colors, prompt)

        if self.prompt is not None:
            x += len(self.prompt)
            w -= len(self.prompt)
            if w < 1:
                w = 1

        self.textfield = CommandField(self, x, self.bounds.y, w, colors,
                                      True, inputfilter)

    def resize_event(self):
        '''the terminal was resized'''

        self.frame.w = self.bounds.w = self.rect.w = textmode.VIDEO.w
        self.frame.y = self.bounds.y = self.rect.y = textmode.VIDEO.h - 1

        w = textmode.VIDEO.w
        if self.prompt is not None:
            w -= len(self.prompt)
            if w < 1:
                w = 1

        self.textfield.y = textmode.VIDEO.h - 1
        self.textfield.w = w

class CommandField(textmode.TextField):
    '''command bar edit field
    Same as TextField, but backspace can exit the command mode
    '''

    def __init__(self, parent, x, y, w, colors, history=True,
                 inputfilter=None):
        '''initialize'''

        super(CommandField, self).__init__(parent, x, y, w, colors, history,
                                           inputfilter)

    def runloop(self):
        '''run the CommandField
        Same as TextField, but backspace can exit
        '''

        # reset the text
        self.text = ''
        self.cursor = 0
        self.draw()

        self.gain_focus()

        while True:
            key = getch()
            if key == KEY_ESC:
                self.text = ''
                self.cursor = 0
                self.lose_focus()
                self.clear()
                return textmode.RETURN_TO_PREVIOUS

            elif key == KEY_BTAB:
                self.lose_focus()
                self.clear()
                return textmode.BACK

            elif key == KEY_TAB:
                self.lose_focus()
                self.clear()
                return textmode.NEXT

            elif key == KEY_RETURN:
                self.add_history()
                self.lose_focus()
                self.clear()
                return textmode.ENTER

            elif key == KEY_BS:
                if self.cursor > 0:
                    self.text = (self.text[:self.cursor - 1] +
                                 self.text[self.cursor:])
                    self.cursor -= 1
                    self.draw()

                elif self.cursor == 0 and not self.text:
                    # exit
                    self.lose_focus()
                    self.clear()
                    return textmode.RETURN_TO_PREVIOUS

            elif key == KEY_DEL:
                if self.cursor < len(self.text):
                    self.text = (self.text[:self.cursor] +
                                 self.text[self.cursor + 1:])
                    self.draw()

                elif self.cursor == 0 and not self.text:
                    # exit
                    self.lose_focus()
                    self.clear()
                    return textmode.RETURN_TO_PREVIOUS

            elif key == KEY_LEFT:
                if self.cursor > 0:
                    self.cursor -= 1
                    self.draw()

            elif key == KEY_RIGHT:
                if self.cursor < len(self.text):
                    self.cursor += 1
                    self.draw()

            elif key == KEY_HOME:
                if self.cursor > 0:
                    self.cursor = 0
                    self.draw()

            elif key == KEY_END:
                if self.cursor != len(self.text):
                    self.cursor = len(self.text)
                    self.draw()

            elif key == KEY_UP:
                self.recall_up()

            elif key == KEY_DOWN:
                self.recall_down()

            elif len(key) == 1 and len(self.text) < self.w:
                if self.inputfilter is not None:
                    ch = self.inputfilter(key)
                else:
                    ch = self.default_inputfilter(key)

                if ch is not None:
                    self.text = (self.text[:self.cursor] + ch +
                                 self.text[self.cursor:])
                    self.cursor += 1
                    self.draw()



class HelpWindow(textmode.TextWindow):
    '''displays usage information'''

    def __init__(self, parent):
        '''initialize'''

        self.parent = parent

        text = '''Commands
 :help    :?          Show this information
 :about               Show About box
 :q       :q!         Quit

 :0                   Go to top

Command keys
 :                    Enter command mode
 /        Ctrl-F      Find
 ?                    Find backwards
 n        Ctrl-G      Find again
 x        Ctrl-X      Find hexadecimal

 1                    View single bytes
 2                    View 16-bit words
 3                    View 16-bit words, swapped
 4                    View 32-bit words
 5                    View 32-bit words, swapped
 <                    Roll left
 >                    Roll right
 v        Ctrl-V      Toggle selection mode

 @                    Jump to address
 m                    Mark; copy address to
                            jump history
 +                    Add offset
 -                    Minus offset

 hjkl     arrows      Move cursor
 Ctrl-U   PageUp      Go one page up
 Ctrl-V   PageDown    Go one page down
 g        Home        Go to top
 G        End         Go to end
 ^        0           Go to start of line
 $                    Go to end of line
 H                    Go to top of screen
 M                    Go to middle of screen
 L                    Go to bottom of screen
 w                    Go to next ASCII word
 b                    Go to previous ASCII word

 Ctrl-R               Redraw screen
 Ctrl-Q               Force quit'''

        colors = textmode.ColorSet(BLACK, WHITE)
        colors.title = textmode.video_color(RED, WHITE)
        colors.cursor = textmode.video_color(BLACK, GREEN)

        w = 52
        h = self.parent.frame.h - 6
        if h < 4:
            h = 4
        x = textmode.center_x(w, self.parent.frame.w)
        y = textmode.center_y(h, self.parent.frame.h)

        super(HelpWindow, self).__init__(x, y, w, h, colors, title='Help',
                                         border=True, text=text.split('\n'),
                                         scrollbar=False, status=False)

    def resize_event(self):
        '''the terminal was resized'''

        # Note: this works alright because the HelpWindow
        # is always on top of its parent window ...

        w = self.frame.w
        h = self.parent.frame.h - 6
        if h < 4:
            h = 4
        x = textmode.center_x(w, self.parent.frame.w)
        y = textmode.center_y(h, self.parent.frame.h)

        self.frame = Rect(x, y, w, h)

        # bounds is the inner area; for view content
        if self.has_border:
            self.bounds = Rect(x + 1, y + 1, w - 2, h - 2)
        else:
            self.bounds = self.frame

        # rect is the outer area; larger because of shadow
        self.rect = Rect(x, y, w + 2, h + 1)

        if self.cursor >= self.bounds.h:
            self.cursor = self.bounds.h - 1

        if self.top > len(self.text) - self.bounds.h:
            self.top = len(self.text) - self.bounds.h
            if self.top < 0:
                self.top = 0

    def runloop(self):
        '''run the Help window'''

        # this is the same as for TextWindow, but the
        # hexview app uses some more navigation keys

        while True:
            key = getch()

            if key == KEY_ESC or key == ' ' or key == KEY_RETURN:
                self.lose_focus()
                return textmode.RETURN_TO_PREVIOUS

            elif key == KEY_UP or key == 'k':
                self.move_up()

            elif key == KEY_DOWN or key == 'j':
                self.move_down()

            elif key == KEY_PAGEUP or key == 'Ctrl-U':
                self.pageup()

            elif key == KEY_PAGEDOWN or key == 'Ctrl-V':
                self.pagedown()

            elif key == KEY_HOME or key == 'g':
                self.goto_top()

            elif key == KEY_END or key == 'G':
                self.goto_bottom()



class AboutBox(textmode.Alert):
    '''about box'''

    def __init__(self):
        '''initialize'''

        text = '''HexView
--------%s
version %s

Copyright 2016 by
Walter de Jong <walter@heiho.net>''' % ('-' * len(VERSION), VERSION)

        colors = textmode.ColorSet(BLACK, WHITE)
        colors.title = textmode.video_color(RED, WHITE)
        colors.button = textmode.video_color(WHITE, BLUE, bold=True)
        colors.buttonhotkey = textmode.video_color(YELLOW, BLUE, bold=True)
        colors.activebutton = textmode.video_color(WHITE, GREEN, bold=True)
        colors.activebuttonhotkey = textmode.video_color(YELLOW, GREEN,
                                                         bold=True)
        super(AboutBox, self).__init__(colors, 'About', text)

    def draw(self):
        '''draw the About box'''

        super(AboutBox, self).draw()

        # draw pretty horizontal line in text
        w = len(VERSION) + 8
        x = self.bounds.x + textmode.center_x(w, self.bounds.w)
        textmode.VIDEO.hline(x, self.frame.y + 3, w, curses.ACS_HLINE,
                    self.colors.text)



def hexview_main():
    '''main program'''

    colors = textmode.ColorSet(BLACK, CYAN)
    colors.cursor = textmode.video_color(WHITE, BLACK, bold=True)
    colors.status = colors.cursor
    colors.invisibles = textmode.video_color(BLUE, CYAN, bold=True)

    view = HexWindow(0, 0, 80, textmode.VIDEO.h - 1, colors)
    view.load(sys.argv[1])
    view.show()

    textmode.VIDEO.puts(0, textmode.VIDEO.h - 1,
                        'Enter :help for usage information',
                        textmode.video_color(WHITE, BLACK))
    view.runloop()



if __name__ == '__main__':
    import os
    import sys

    if len(sys.argv) <= 1:
        print 'usage: %s <filename>' % os.path.basename(sys.argv[0])
        sys.exit(1)

    textmode.init()

    try:
        hexview_main()
    finally:
        textmode.terminate()

# EOB

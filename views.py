#
#   views.py     WJ116
#

'''(n)curses console text mode UI'''

import curses
import os
import sys
import time
import traceback
import re

from curses import COLOR_WHITE, COLOR_YELLOW, COLOR_GREEN, COLOR_CYAN, \
                   COLOR_BLUE, COLOR_MAGENTA, COLOR_RED, COLOR_BLACK

# the 'stdscr' variable
SCREEN = None

# screen dimensions
SCREEN_W = None
SCREEN_H = None

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

BOLD = curses.A_BOLD
REVERSE = curses.A_REVERSE

STACK = []

REGEX_HOTKEY = re.compile(r'<((Ctrl-)?[a-zA-Z0-9])>')

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


class Rect(object):
    '''represents a rectangle'''

    def __init__(self, x, y, w, h):
        '''initialize'''

        self.x = x
        self.y = y
        self.w = w
        self.h = h



class View(object):
    '''represents an onscreen window'''

    def __init__(self, x, y, w, h, title=None, border=True, textcolor=0,
                 bordercolor=0, titlecolor=0, statuscolor=0):
        '''initialize'''

        # Note: If you choose textcolor in reverse-video, then the entire
        # window will be with reversed colors
        # That's just the way it is ... do not choose textcolor REVERSE

        # Note: for windows with a statusbar, you should do self.bounds.h -= 1

        assert w > 0
        assert h > 0

        self.frame = Rect(x, y, w, h)
        self.title = title
        self.has_border = border
        if self.has_border:
            self.bounds = Rect(1, 1, w - 2, h - 2)
        else:
            self.bounds = Rect(0, 0, w, h)
            if self.title is not None:
                self.bounds.y += 1
                self.bounds.h -= 1

        assert self.bounds.w > 0
        assert self.bounds.h > 0

        self.textcolor = textcolor
        self.bordercolor = bordercolor
        if self.bordercolor == 0:
            self.bordercolor = self.textcolor
        self.titlecolor = titlecolor
        if self.titlecolor == 0:
            self.titlecolor = self.textcolor
        self.statuscolor = statuscolor
        if self.statuscolor == 0:
            self.statuscolor = self.textcolor

        self.visible = False
        self.needs_update = False
        self.statusbar_msg = None

        self.win = curses.newwin(h, w, y, x)
        self.win.attrset(self.textcolor)
        self.win.bkgdset(self.textcolor)

    def draw(self):
        '''draw the window'''

        self.win.clear()
        self.needs_update = True

        if self.has_border:
            self.win.attrset(self.bordercolor)
            self.win.box()

        self.draw_title()
        self.draw_statusbar()
        self.win.attrset(self.textcolor)

    def draw_title(self):
        '''draw the title'''

        if self.title is None:
            return

        self.win.attrset(self.titlecolor)

        if not self.has_border:
            self.win.hline(0, 0, ' ', self.frame.w)

        title_str = ' ' + self.title + ' '

        if len(title_str) > self.frame.w - 4:
            title_str = ' ' + self.title[(self.frame.w - 7):] + '... '

        self.win.addstr(0, (self.frame.w - len(title_str)) / 2,
                        title_str)

        self.needs_update = True

    def draw_statusbar(self):
        '''draw the status bar'''

        if self.statusbar_msg is None:
            return

        # erase former statusbar message
        if self.has_border:
            line_char = curses.ACS_HLINE
            xpos = 1
            self.win.attrset(self.bordercolor)
        else:
            line_char = ' '
            xpos = 0
            self.win.attrset(self.statuscolor)

        self.win.hline(self.frame.h - 1, xpos, line_char, self.bounds.w)

        self.win.attrset(self.statuscolor)

        line = ' ' + self.statusbar_msg + ' '
        self.win.addstr(self.frame.h - 1, self.frame.w - len(line) - 2,
                        line)

        self.needs_update = True

    def statusbar(self, msg):
        '''update statusbar'''

        if self.statusbar_msg == msg:
            return

        self.statusbar_msg = msg
        self.draw_statusbar()

    def update(self):
        '''redraw window'''

        if self.needs_update and self.visible:
            self.win.refresh()
            self.needs_update = False

    def show(self):
        '''show the window'''

        if not self.visible:
            self.visible = True
            self.win.attrset(self.textcolor)
            self.win.bkgdset(self.textcolor)
            self.draw()
            self.update()

    def hide(self):
        '''hide the window'''

        if self.visible:
            self.win.attrset(curses.color_pair(0))
            self.win.bkgdset(curses.color_pair(0))
            self.win.clear()
            self.needs_update = True
            self.update()
            self.visible = False
            # Note: redraw of underlying window is needed

    def close(self):
        '''close the window'''

        if self.win is not None:
            self.hide()
            self.win = None

    def wput(self, x, y, msg, attr=0):
        '''print message in window at relative position
        Does not clear to end of line
        '''

        xpos = self.bounds.x + x
        if xpos >= self.frame.w:
            # clipped outside view
            return

        ypos = self.bounds.y + y
        if ypos > self.bounds.h:
            # clipped outside view
            return

        if xpos + len(msg) >= self.bounds.w:
            # clip message
            msg = msg[:(self.bounds.w - xpos)]

        if attr == 0:
            attr = self.textcolor

        self.win.addstr(ypos, xpos, msg, attr)
        self.needs_update = True

    def wprint(self, x, y, msg, attr=0):
        '''print message in window at relative position
        Clears to end of line
        '''

        xpos = self.bounds.x + x
        if xpos >= self.frame.w:
            # clipped outside view
            return

        ypos = self.bounds.y + y
        if ypos >= self.frame.h:
            # clipped outside view
            return

        if x + len(msg) > self.bounds.w:
            # clip message
            msg = msg[:(self.bounds.w - x)]

        elif x + len(msg) < self.bounds.w:
            # extend message to border
            # this clears to end of line, without overwriting the border
            msg += ' ' * (self.bounds.w - (x + len(msg)))

        if attr == 0:
            attr = self.textcolor

        self.win.addstr(self.bounds.y + y, self.bounds.x + x, msg, attr)
        self.needs_update = True



class TextView(View):
    '''a window for displaying text'''

    def __init__(self, x, y, w, h, title=None, border=True, textcolor=0,
                 bordercolor=0, titlecolor=0, statuscolor=0,
                 cursorcolor=0, text=None):
        '''initialize'''

        super(TextView, self).__init__(x, y, w, h, title, border, textcolor,
                                       bordercolor, titlecolor, statuscolor)

        if not self.has_border:
            # subtract one for statusbar
            self.bounds.h -= 1
            assert self.bounds.h > 0

        self.cursorcolor = cursorcolor
        if self.cursorcolor == 0:
            self.cursorcolor = self.textcolor

        self.text = text
        if self.text is None:
            self.text = []

        self.top = 0
        self.cursor = 0
        self.xoffset = 0

    def draw(self):
        '''draw the window'''

        super(TextView, self).draw()
        self.draw_text()

    def draw_text(self):
        '''redraws the text content'''

        y = 0
        while y < self.bounds.h:
            try:
                self.printline(y)
            except IndexError:
                break

            y += 1

        self.draw_cursor()

    def clear_cursor(self):
        '''erase the cursor'''

        self.printline(self.cursor)
        self.needs_update = True

    def draw_cursor(self):
        '''redraw the cursor line'''

        self.printline(self.cursor, self.cursorcolor)
        self.statusbar('%d,%d' % ((self.top + self.cursor + 1),
                                  (self.xoffset + 1)))
        self.needs_update = True

    def printline(self, y, attr=0):
        '''print a single line'''

        self.wprint(0, y, self.text[self.top + y][self.xoffset:], attr)

    def selection(self):
        '''Returns currently selected line'''

        return self.text[self.top + self.cursor]

    def load(self, filename):
        '''load text file
        raises IOError on error
        '''

        f = open(filename)
        with f:
            self.text = f.readlines()

        # strip newlines
        self.text = [x.rstrip() for x in self.text]

        if self.title is not None:
            self.title = os.path.basename(filename)
            # do a full draw because the title has changed
            self.draw()

    def move_up(self):
        '''move up'''

        if self.cursor > 0:
            self.clear_cursor()
            self.cursor -= 1
            self.draw_cursor()
        else:
            self.scroll_up()

    def move_down(self):
        '''move down'''

        if self.cursor < self.bounds.h - 1:
            self.clear_cursor()
            self.cursor += 1
            self.draw_cursor()
        else:
            self.scroll_down()

    def move_left(self):
        '''move left'''

        if self.xoffset > 0:
            self.xoffset -= 4
            if self.xoffset < 0:
                self.xoffset = 0
            self.draw_text()

    def move_right(self):
        '''move right'''

        max_xoffset = 500
        if self.xoffset < max_xoffset:
            self.xoffset += 4
            self.draw_text()

    def scroll_up(self):
        '''scroll up'''

        old_top = self.top
        self.top -= 1
        if self.top < 0:
            self.top = 0

        if self.top != old_top:
            self.draw_text()

    def scroll_down(self):
        '''scroll down'''

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
            self.draw_cursor()

    def runloop(self):
        '''control the textview'''

        self.show()

        while True:
            key = getch()

            if key == KEY_ESC:
                self.close()
                return KEY_ESC

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

            else:
                return key

            self.update()



class Widget(object):
    '''represents a widget'''

    def __init__(self, parent, x, y):
        '''initialize'''

        self.parent = parent
        self.x = x
        self.y = y

    def draw(self):
        '''draw widget'''

        pass



class Button(Widget):
    '''represents a button'''

    def __init__(self, parent, x, y, label, activecolor=0, inactivecolor=0,
                 hotkeycolor=0):
        '''initialize'''

        assert label is not None

        super(Button, self).__init__(parent, x, y)

        self.label = label
        self.activecolor = activecolor
        self.inactivecolor = inactivecolor
        self.hotkeycolor = hotkeycolor

        self.active = False
        self.pushing = False

    def draw(self):
        '''draw button'''

        label = self.label
        hotkey = label_hotkey(label)
        if hotkey is not None:
            hotkey_pos = label.find('<')
            # strip out hooks
            label = label.replace('<', '')
            label = label.replace('>', '')
        else:
            hotkey_pos = None

        add = 1
        text = ' ' + label + ' '
        if len(text) <= 5:
            # minimum width is 7
            text = ' ' + text + ' '
            add += 1

        if self.active:
            text = '>' + text + '<'
            attr = self.activecolor
        else:
            text = ' ' + text + ' '
            attr = self.inactivecolor
        add += 1

        xpos = self.x
        if self.pushing:
            xpos += 1

        self.parent.wput(xpos, self.y, text, attr)

        if hotkey_pos is not None:
            # draw hotkey
            attr = self.hotkeycolor
            if attr == 0:
                if self.active:
                    attr = self.activecolor
                else:
                    attr = self.inactivecolor

            self.parent.wput(xpos + hotkey_pos + add, self.y, hotkey, attr)

    def select(self):
        '''select button'''

        self.active = True

    def deselect(self):
        '''deactivate button'''

        self.active = False

    def push(self):
        '''push the button'''

        assert self.active

        # animate button
        self.pushing = True
        self.parent.draw()
        self.parent.update()
        time.sleep(0.1)

        self.pushing = False
        self.parent.draw()
        self.parent.update()
        time.sleep(0.1)


class Alert(View):
    '''an alert box with buttons'''

    def __init__(self, msg, title=None, border=True, textcolor=0,
                 bordercolor=0, titlecolor=0, buttons=None, default=0,
                 activecolor=0, inactivecolor=0, hotkeycolor=0):
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
        elif title is not None:
            h += 1

        # center the box
        x = center_x(w)
        y = center_y(h)

        super(Alert, self).__init__(x, y, w, h, title, border, textcolor,
                                    bordercolor, titlecolor)

        self.text = lines

        # y position of the button bar
        y = self.bounds.h - 2
        assert y > 0

        self.hotkeys = []

        if buttons is None:
            # one OK button: center it
            label = '<O>K'
            x = center_x(button_width(label), self.bounds.w)
            self.buttons = [Button(self, x, y, label, activecolor,
                                   inactivecolor, hotkeycolor),]
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
                button = Button(self, int(x), y, label, activecolor,
                                inactivecolor, hotkeycolor)
                self.buttons.append(button)
                x += spacing + button_width(label)

                # save hotkey
                hotkey = label_hotkey(label)
                self.hotkeys.append(hotkey)

        assert default >= 0 and default < len(self.buttons)
        self.cursor = default
        self.buttons[self.cursor].select()

    def draw(self):
        '''draw the alert box'''

        super(Alert, self).draw()

        # draw the text
        y = 1
        for line in self.text:
            x = (self.bounds.w - len(line)) / 2
            self.wprint(x, y, line)
            y += 1

        # draw buttons
        self.draw_buttons()

    def draw_buttons(self):
        '''draw the buttons'''

        for button in self.buttons:
            button.draw()

        self.needs_update = True

    def move_right(self):
        '''select button to the right'''

        if len(self.buttons) <= 1:
            return

        self.buttons[self.cursor].deselect()
        self.cursor += 1
        if self.cursor >= len(self.buttons):
            self.cursor = 0
        self.buttons[self.cursor].select()
        self.draw_buttons()

    def move_left(self):
        '''select button to the left'''

        if len(self.buttons) <= 1:
            return

        self.buttons[self.cursor].deselect()
        self.cursor -= 1
        if self.cursor < 0:
            self.cursor = len(self.buttons) - 1
        self.buttons[self.cursor].select()
        self.draw_buttons()

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
                    self.buttons[self.cursor].deselect()
                    self.cursor = idx
                    self.buttons[self.cursor].select()

                self.push()
                return True

            idx += 1

        return False

    def runloop(self):
        '''control the alertbox'''

        self.show()

        while True:
            key = getch()

            if key == KEY_ESC:
                self.close()
                return -1

            if key == KEY_RETURN or key == ' ':
                self.push()
                self.close()
                return self.cursor

            if key == KEY_TAB or key == KEY_RIGHT:
                self.move_right()

            elif key == KEY_BTAB or key == KEY_LEFT:
                self.move_left()

            elif self.push_hotkey(key):
                return self.cursor

            self.update()



def init():
    '''initialize'''

    global SCREEN, SCREEN_W, SCREEN_H

    SCREEN = curses.initscr()
    curses.savetty()
    curses.start_color()
    curses.noecho()
    SCREEN.keypad(1)
    curses.raw()
    curses.curs_set(0)

    SCREEN_H, SCREEN_W = SCREEN.getmaxyx()

    # odd ... screen must be refreshed at least once,
    # or things won't work as expected
    SCREEN.refresh()


def terminate():
    '''end the curses window mode'''

    if SCREEN is not None:
        curses.curs_set(1)
        curses.nocbreak()
        SCREEN.keypad(0)
        curses.echo()
        curses.resetty()
        curses.endwin()

    dump_debug()


def getch():
    '''get keyboard input
    Returns key as a string value
    '''

    key = SCREEN.getch()
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


def ctrl(key):
    '''Returns keycode for when Ctrl is pressed'''

    # Ctrl-A = 1
    # Ctrl-B = 2
    # etc.

    return 'Ctrl-' + key


# curses color pairs suck, but that's just how it is
def set_color(n, fg, bg):
    '''set color pair'''

    assert n < curses.COLOR_PAIRS

    curses.init_pair(n, fg, bg)


def color(n):
    '''Returns color pair'''

    assert n < curses.COLOR_PAIRS

    return curses.color_pair(n)


def label_hotkey(label):
    '''Returns the hotkey in the label
    or None if there is none

    Mind that hotkeys are uppercase, or may also be "Ctrl-key"
    '''

    m = REGEX_HOTKEY.match(label)
    if m is None:
        return None

    hotkey = m.groups()[0]
    if len(hotkey) == 1:
        hotkey = hotkey.upper()
    return hotkey


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
        area = SCREEN_W

    x = (area - width) * 0.5

    # round up for funny looking non-centered objects
    return int(x + 0.5)


def center_y(height, area=0):
    '''Return centered y coordinate
    If area is not given, put it halfway the top of screen
    '''

    if area == 0:
        area = SCREEN_H

    y = (area - height) * 0.3
    return int(y + 0.5)


def push(view):
    '''push a window onto the stack'''

    assert isinstance(view, View)

    STACK.append(view)


def pop():
    '''remove window from stack'''

    try:
        view = STACK.pop()
    except IndexError:
        return
    else:
        view.close()


def top():
    '''Return top view'''

    try:
        return STACK[-1]
    except IndexError:
        return None


def front(view):
    '''Move view to front'''

    assert isinstance(view, View)

    STACK.remove(view)
    push(view)
    view.needs_update = True
    view.update()


def back(view):
    '''Move view to back'''

    STACK.remove(view)
    STACK.insert(0, view)
    update()


def update():
    '''update all windows'''

    for view in STACK:
        if view.visible:
            view.win.touchwin()
            view.win.noutrefresh()
            view.needs_update = False

    curses.doupdate()


def _unit_test():
    '''tests this module'''

    init()

    # color(0) is always WHITE on BLACK (non-bold)
    set_color(1, COLOR_WHITE, COLOR_BLACK)
    set_color(2, COLOR_BLACK, COLOR_WHITE)
    set_color(3, COLOR_WHITE, COLOR_BLUE)
    set_color(4, COLOR_CYAN, COLOR_BLUE)
    set_color(5, COLOR_CYAN, COLOR_BLACK)
    set_color(6, COLOR_WHITE, COLOR_GREEN)
    set_color(7, COLOR_BLACK, COLOR_GREEN)
    set_color(8, COLOR_YELLOW, COLOR_RED)

    view = TextView(5, 3, 75, 20, title='hello', border=True,
                    textcolor=color(3) | BOLD, bordercolor=color(4),
                    titlecolor=color(5) | REVERSE, statuscolor=color(4),
                    cursorcolor=color(1) | BOLD)
    view.load('views.py')
    push(view)
    view.show()

    alert = Alert('Failed to load file', title='Alert', border=True,
                  textcolor=color(2), titlecolor=color(8) | BOLD,
                  bordercolor=0, buttons=['<C>ancel', '<O>K'], default=1,
                  activecolor=color(6) | BOLD, inactivecolor=color(7),
                  hotkeycolor=color(6) | BOLD)
    push(alert)
    returncode = alert.runloop()
    if returncode == -1:
        sys.exit(-1)

    pop()
    update()
    view = top()
    selection = None
    while True:
        key = view.runloop()

        if key == KEY_ESC:
            break

        elif key == ctrl('Q'):
            break

        elif key == KEY_RETURN:
            selection = view.selection()
            break

        view.update()

    view.close()
    terminate()

    if selection != None:
        print 'selection was: "%s"' % selection



if __name__ == '__main__':
    try:
        _unit_test()
#    except SystemExit:
#        terminate()
#        pass
    except:
        terminate()
        traceback.print_exc()

# EOB

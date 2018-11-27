"""test for Menu"""
import os
import unittest

from mock import patch, Mock

try:
    from ui import Menu
    from ui.base_list_ui import Canvas
    fonts_dir = "ui/fonts"
except ImportError:
    print("Absolute imports failed, trying relative imports")
    os.sys.path.append(os.path.dirname(os.path.abspath('.')))
    # Store original __import__
    orig_import = __import__

    def import_mock(name, *args):
        if name in ['helpers']:
            return Mock()
        elif name == 'ui.utils':
            import utils
            return utils
        return orig_import(name, *args)

    with patch('__builtin__.__import__', side_effect=import_mock):
        from menu import Menu
        from base_list_ui import Canvas
        fonts_dir = "../fonts"

def get_mock_input():
    return Mock()

def get_mock_output(rows=8, cols=21):
    m = Mock()
    m.configure_mock(rows=rows, cols=cols, type=["char"])
    return m

def get_mock_graphical_output(width=128, height=64, mode="1", cw=6, ch=8):
    m = get_mock_output(rows=width/cw, cols=height/ch)
    m.configure_mock(width=width, height=height, device_mode=mode, char_height=ch, char_width=cw, type=["b&w-pixel"])
    return m

mu_name = "Test menu"


class TestMenu(unittest.TestCase):
    """tests menu class"""

    def test_constructor(self):
        """tests constructor"""
        menu = Menu([["Option", "option"]], get_mock_input(), get_mock_output(), name=mu_name, config={})
        self.assertIsNotNone(menu)

    def test_keymap(self):
        """tests keymap"""
        menu = Menu([["Option", "option"]], get_mock_input(), get_mock_output(), name=mu_name, config={})
        self.assertIsNotNone(menu.keymap)
        for key_name, callback in menu.keymap.iteritems():
            self.assertIsNotNone(callback)

    @unittest.skip("expected to fail since menu doesn't handle exit label replacement yet")
    def test_exit_label_leakage(self):
        """tests whether the exit label of one Menu leaks into another"""
        i = get_mock_input()
        o = get_mock_output()
        c1 = Menu([["a", "1"]], i, o, name=mu_name + "1", final_button_name="Name1", config={})
        c2 = Menu([["b", "2"]], i, o, name=mu_name + "2", final_button_name="Name2", config={})
        c3 = Menu([["c", "3"]], i, o, name=mu_name + "3", config={})
        assert (c1.exit_entry != c2.exit_entry)
        assert (c2.exit_entry != c3.exit_entry)
        assert (c1.exit_entry != c3.exit_entry)

    def test_left_key_disabled_when_not_exitable(self):
        """Tests whether a menu does not exit on KEY_LEFT when exitable is set to False"""
        num_elements = 3
        contents = [["A" + str(i), "a" + str(i)] for i in range(num_elements)]
        mu = Menu(contents, get_mock_input(), get_mock_output(), name=mu_name, exitable=False, config={})
        mu.refresh = lambda *args, **kwargs: None

        def scenario():
            assert "KEY_LEFT" not in mu.keymap  # KEY_LEFT
            mu.deactivate()
            assert not mu.in_foreground

        with patch.object(mu, 'idle_loop', side_effect=scenario) as p:
            mu.activate()

    def test_left_key_returns_none(self):
        """ A Menu is never supposed to return anything other than None"""
        num_elements = 3
        contents = [["A" + str(i), "a" + str(i)] for i in range(num_elements)]
        mu = Menu(contents, get_mock_input(), get_mock_output(), name=mu_name, config={})
        mu.refresh = lambda *args, **kwargs: None

        # Checking at the start of the list
        def scenario():
            mu.deactivate()  # KEY_LEFT
            assert not mu.in_foreground

        with patch.object(mu, 'idle_loop', side_effect=scenario) as p:
            return_value = mu.activate()
        assert return_value is None

        # Checking at the end of the list
        def scenario():
            for i in range(num_elements):
                mu.move_down()  # KEY_DOWN x3
            mu.deactivate()  # KEY_LEFT
            assert not mu.in_foreground

        with patch.object(mu, 'idle_loop', side_effect=scenario) as p:
            return_value = mu.activate()
        assert return_value is None

    def test_graphical_display_redraw(self):
        num_elements = 1
        o = get_mock_graphical_output()
        contents = [["A" + str(i), "a" + str(i)] for i in range(num_elements)]
        mu = Menu(contents, get_mock_input(), o, name=mu_name, config={})
        Canvas.fonts_dir = fonts_dir
        # Exiting immediately, but we should get at least one redraw
        def scenario():
            mu.deactivate()  # KEY_LEFT
            assert not mu.in_foreground

        with patch.object(mu, 'idle_loop', side_effect=scenario) as p:
            return_value = mu.activate()
        assert o.display_image.called
        assert o.display_image.call_count == 1 #One in to_foreground

    def test_graphical_redraw_with_eh_2(self):
        """
        Tests for a bug where a menu with one two-elements-high entry would fail to render
        """
        num_elements = 3
        o = get_mock_graphical_output()
        contents = [[["A" + str(i), "B"+str(i)], "a" + str(i)] for i in range(num_elements)]
        mu = Menu(contents, get_mock_input(), o, name=mu_name, entry_height=2, append_exit=False, config={})
        Canvas.fonts_dir = fonts_dir
        # Exiting immediately, but we should get at least one redraw
        def scenario():
            mu.deactivate()  # KEY_LEFT
            assert not mu.in_foreground

        with patch.object(mu, 'idle_loop', side_effect=scenario) as p:
            return_value = mu.activate()
        assert o.display_image.called
        assert o.display_image.call_count == 1 #One in to_foreground

    def test_callback_is_executed(self):
        num_elements = 3
        contents = [["A" + str(i), "a" + str(i)] for i in range(num_elements)]
        cb1 = Mock()
        cb2 = Mock()
        contents[0][1] = cb1
        contents[1][1] = cb2

        mu = Menu(contents, get_mock_input(), get_mock_output(), name=mu_name, config={})
        mu.refresh = lambda *args, **kwargs: None

        # Checking at other elements - shouldn't return
        def scenario():
            mu.select_entry()  # KEY_ENTER
            assert cb1.called
            assert mu.in_foreground
            mu.move_down() # KEY_DOWN
            mu.select_entry()  # KEY_ENTER
            assert cb2.called
            assert mu.in_foreground
            mu.deactivate()  # because is not deactivated yet and would idle loop otherwise
            assert not mu.in_foreground

        with patch.object(mu, 'idle_loop', side_effect=scenario) as p:
            return_value = mu.activate()
        assert return_value is None

    def test_shows_data_on_screen(self):
        """Tests whether the Menu outputs data on screen when it's ran"""
        num_elements = 3
        contents = [["A" + str(i), "a" + str(i)] for i in range(num_elements)]
        i = get_mock_input()
        o = get_mock_output()
        mu = Menu(contents, i, o, name=mu_name, config={})

        def scenario():
            mu.deactivate()

        with patch.object(mu, 'idle_loop', side_effect=scenario) as p:
            mu.activate()
            #The scenario should only be called once
            assert mu.idle_loop.called
            assert mu.idle_loop.call_count == 1

        assert o.display_data.called
        assert o.display_data.call_count == 1 #One in to_foreground
        assert o.display_data.call_args[0] == ('A0', 'A1', 'A2', 'Back')

if __name__ == '__main__':
    unittest.main()

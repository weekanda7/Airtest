# -*- coding: utf-8 -*-
"""
This module contains the Airtest Core APIs.
"""
import os
import time
from typing import Dict, Tuple
from six.moves.urllib.parse import parse_qsl, urlparse

from airtest.core.cv import Template, loop_find, try_log_screen
from airtest.core.error import TargetNotFoundError
from airtest.core.settings import Settings as ST
from airtest.utils.compat import script_log_dir
from airtest.core.helper import (G, delay_after_operation, import_device_cls, logwrap, set_logdir, using, log)
# Assertions
from airtest.core.assertions import (
    assert_exists,
    assert_not_exists,
    assert_equal,
    assert_not_equal,  # noqa
    assert_true,
    assert_false,
    assert_is,
    assert_is_not,
    assert_is_none,
    assert_is_not_none,
    assert_in,
    assert_not_in,
    assert_is_instance,
    assert_not_is_instance)
import cv2
from PIL import Image

from PyQt6.QtGui import QImage, QPixmap
LOWEST_THRESHOLD = 0.6
"""
Device Setup APIs
"""


def init_device(platform="Android", uuid=None, **kwargs):
    """
    Initialize device if not yet, and set as current device.

    :param platform: Android, IOS or Windows
    :param uuid: uuid for target device, e.g. serialno for Android, handle for Windows, uuid for iOS
    :param kwargs: Optional platform specific keyword args, e.g. `cap_method=JAVACAP` for Android
    :return: device instance
    :Example:

        >>> init_device(platform="Android",uuid="SJE5T17B17", cap_method="JAVACAP")
        >>> init_device(platform="Windows",uuid="123456")
    """
    platform = platform.lower()
    cls = import_device_cls(platform)
    if platform == "ios":
        dev = cls(uuid=uuid, **kwargs)
    else:
        dev = cls(uuid, **kwargs)
    # Add device instance in G and set as current device.
    G.add_device(dev)
    return dev


def connect_device(uri):
    """
    Initialize device with uri, and set as current device.

    :param uri: an URI where to connect to device, e.g. `android://adbhost:adbport/serialno?param=value&param2=value2`
    :return: device instance
    :Example:

        >>> connect_device("Android:///")  # local adb device using default params
        >>> # local device with serial number SJE5T17B17 and custom params
        >>> connect_device("Android:///SJE5T17B17?cap_method=javacap&touch_method=adb")
        >>> # remote device using custom params Android://adbhost:adbport/serialno
        >>> connect_device("Android://127.0.0.1:5037/10.254.60.1:5555")
        >>> connect_device("Windows:///")  # connect to the desktop
        >>> connect_device("Windows:///123456")  # Connect to the window with handle 123456
        >>> connect_device("windows:///?title_re='.*explorer.*'")  # Connect to the window that name include "explorer"
        >>> connect_device("Windows:///123456?foreground=False")  # Connect to the window without setting it foreground
        >>> connect_device("iOS:///127.0.0.1:8100")  # iOS device
        >>> connect_device("iOS:///http://localhost:8100/?mjpeg_port=9100")  # iOS with mjpeg port
        >>> connect_device("iOS:///http://localhost:8100/?mjpeg_port=9100&&udid=00008020-001270842E88002E")  # iOS with mjpeg port and udid
        >>> connect_device("iOS:///http://localhost:8100/?mjpeg_port=9100&&uuid=00008020-001270842E88002E")  # udid/uuid/serialno are all ok

    """
    d = urlparse(uri)
    platform = d.scheme
    host = d.netloc
    uuid = d.path.lstrip("/")
    params = dict(parse_qsl(d.query))
    if host:
        params["host"] = host.split(":")
    dev = init_device(platform, uuid, **params)
    return dev


def device():
    """
    Return the current active device.

    :return: current device instance
    :Example:
        >>> dev = device()
        >>> dev.touch((100, 100))
    """
    return G.DEVICE


def set_current(idx):
    """
    Set current active device.

    :param idx: uuid or index of initialized device instance
    :raise IndexError: raised when device idx is not found
    :return: None
    :platforms: Android, iOS, Windows
    :Example:
        >>> # switch to the first phone currently connected
        >>> set_current(0)
        >>> # switch to the phone with serial number serialno1
        >>> set_current("serialno1")

    """

    dev_dict = {dev.uuid: dev for dev in G.DEVICE_LIST}
    if idx in dev_dict:
        current_dev = dev_dict[idx]
    elif isinstance(idx, int) and idx < len(G.DEVICE_LIST):
        current_dev = G.DEVICE_LIST[idx]
    else:
        raise IndexError("device idx not found in: %s or %s" % (list(dev_dict.keys()), list(range(len(G.DEVICE_LIST)))))
    G.DEVICE = current_dev


def auto_setup(basedir=None, devices=None, logdir=None, project_root=None, compress=None):
    """
    Auto setup running env and try connect android device if not device connected.

    :param basedir: basedir of script, __file__ is also acceptable.
    :param devices: connect_device uri in list.
    :param logdir: log dir for script report, default is None for no log, set to ``True`` for ``<basedir>/log``.
    :param project_root: project root dir for `using` api.
    :param compress: The compression rate of the screenshot image, integer in range [1, 99], default is 10
    :Example:
        >>> auto_setup(__file__)
        >>> auto_setup(__file__, devices=["Android://127.0.0.1:5037/SJE5T17B17"],
        ...             logdir=True, project_root=r"D:\\test\\logs", compress=90)
    """
    if basedir:
        if os.path.isfile(basedir):
            basedir = os.path.dirname(basedir)
        if basedir not in G.BASEDIR:
            G.BASEDIR.append(basedir)
    if devices:
        for dev in devices:
            connect_device(dev)
    if logdir:
        logdir = script_log_dir(basedir, logdir)
        set_logdir(logdir)
    if project_root:
        ST.PROJECT_ROOT = project_root
    if compress:
        ST.SNAPSHOT_QUALITY = compress


"""
Device Operations
"""


@logwrap
def shell(cmd):
    """
    Start remote shell in the target device and execute the command

    :param cmd: command to be run on device, e.g. "ls /data/local/tmp"
    :return: the output of the shell cmd
    :platforms: Android
    :Example:
        >>> # Execute commands on the current device adb shell ls
        >>> print(shell("ls"))

        >>> # Execute adb instructions for specific devices
        >>> dev = connect_device("Android:///device1")
        >>> dev.shell("ls")

        >>> # Switch to a device and execute the adb command
        >>> set_current(0)
        >>> shell("ls")
    """
    return G.DEVICE.shell(cmd)


@logwrap
def start_app(package, activity=None):
    """
    Start the target application on device

    :param package: name of the package to be started, e.g. "com.netease.my"
    :param activity: the activity to start, default is None which means the main activity
    :return: None
    :platforms: Android, iOS
    :Example:
        >>> start_app("com.netease.cloudmusic")
        >>> start_app("com.apple.mobilesafari")  # on iOS
    """
    G.DEVICE.start_app(package, activity)


@logwrap
def stop_app(package):
    """
    Stop the target application on device

    :param package: name of the package to stop, see also `start_app`
    :return: None
    :platforms: Android, iOS
    :Example:
        >>> stop_app("com.netease.cloudmusic")
    """
    G.DEVICE.stop_app(package)


@logwrap
def clear_app(package):
    """
    Clear data of the target application on device

    :param package: name of the package,  see also `start_app`
    :return: None
    :platforms: Android
    :Example:
        >>> clear_app("com.netease.cloudmusic")
    """
    G.DEVICE.clear_app(package)


@logwrap
def install(filepath, **kwargs):
    """
    Install application on device

    :param filepath: the path to file to be installed on target device
    :param kwargs: platform specific `kwargs`, please refer to corresponding docs
    :return: None
    :platforms: Android
    :Example:
        >>> install(r"D:\\demo\\test.apk")
        >>> # adb install -r -t D:\\demo\\test.apk
        >>> install(r"D:\\demo\\test.apk", install_options=["-r", "-t"])
    """
    return G.DEVICE.install_app(filepath, **kwargs)


@logwrap
def uninstall(package):
    """
    Uninstall application on device

    :param package: name of the package, see also `start_app`
    :return: None
    :platforms: Android
    :Example:
        >>> uninstall("com.netease.cloudmusic")
    """
    return G.DEVICE.uninstall_app(package)


@logwrap
def snapshot(filename=None, msg="", quality=None, max_size=None):
    """
    Take the screenshot of the target device and save it to the file.

    :param filename: name of the file where to save the screenshot. If the relative path is provided, the default
                     location is ``ST.LOG_DIR``
    :param msg: short description for screenshot, it will be recorded in the report
    :param quality: The image quality, integer in range [1, 99], default is 10
    :param max_size: the maximum size of the picture, e.g 1200
    :return: {"screen": filename, "resolution": resolution of the screen} or None
    :platforms: Android, iOS, Windows
    :Example:
        >>> snapshot(msg="index")
        >>> # save the screenshot to test.jpg
        >>> snapshot(filename="test.png", msg="test")

        The quality and size of the screenshot can be set::

        >>> # Set the screenshot quality to 30
        >>> ST.SNAPSHOT_QUALITY = 30
        >>> # Set the screenshot size not to exceed 600*600
        >>> # if not set, the default size is the original image size
        >>> ST.IMAGE_MAXSIZE = 600
        >>> # The quality of the screenshot is 30, and the size does not exceed 600*600
        >>> touch((100, 100))
        >>> # The quality of the screenshot of this sentence is 90
        >>> snapshot(filename="test.png", msg="test", quality=90)
        >>> # The quality of the screenshot is 90, and the size does not exceed 1200*1200
        >>> snapshot(filename="test2.png", msg="test", quality=90, max_size=1200)

    """
    if not quality:
        quality = ST.SNAPSHOT_QUALITY
    if not max_size and ST.IMAGE_MAXSIZE:
        max_size = ST.IMAGE_MAXSIZE
    if filename:
        if not os.path.isabs(filename):
            logdir = ST.LOG_DIR or "."
            filename = os.path.join(logdir, filename)
        screen = G.DEVICE.snapshot(filename, quality=quality, max_size=max_size)
        return try_log_screen(screen, quality=quality, max_size=max_size)
    else:
        return try_log_screen(quality=quality, max_size=max_size)


@logwrap
def wake():
    """
    Wake up and unlock the target device

    :return: None
    :platforms: Android
    :Example:
        >>> wake()

    .. note:: Might not work on some models
    """
    G.DEVICE.wake()


@logwrap
def home():
    """
    Return to the home screen of the target device.

    :return: None
    :platforms: Android, iOS
    :Example:
        >>> home()
    """
    G.DEVICE.home()


@logwrap
def touch(v, times=1, **kwargs):
    """
    Perform the touch action on the device screen

    :param v: target to touch, either a ``Template`` instance or absolute coordinates (x, y)
    :param times: how many touches to be performed
    :param kwargs: platform specific `kwargs`, please refer to corresponding docs
    :return: finial position to be clicked, e.g. (100, 100)
    :platforms: Android, Windows, iOS
    :Example:
        Click absolute coordinates::

        >>> touch((100, 100))

        Click the center of the picture(Template object)::

        >>> touch(Template(r"tpl1606730579419.png", target_pos=5))

        Click 2 times::

        >>> touch((100, 100), times=2)

        Under Android and Windows platforms, you can set the click duration::

        >>> touch((100, 100), duration=2)

        Right click(Windows)::

        >>> touch((100, 100), right_click=True)

    """
    if isinstance(v, Template):
        pos = loop_find(v, timeout=ST.FIND_TIMEOUT)
    else:
        try_log_screen()
        pos = v
    for _ in range(times):
        G.DEVICE.touch(pos, **kwargs)
        time.sleep(0.05)
        
    delay_after_operation()
    return pos


click = touch  # click is alias of touch


@logwrap
def double_click(v):
    """
    Perform double click

    :param v: target to touch, either a ``Template`` instance or absolute coordinates (x, y)
    :return: finial position to be clicked
    :Example:

        >>> double_click((100, 100))
        >>> double_click(Template(r"tpl1606730579419.png"))
    """
    if isinstance(v, Template):
        pos = loop_find(v, timeout=ST.FIND_TIMEOUT)
    else:
        try_log_screen()
        pos = v
    G.DEVICE.double_click(pos)
    delay_after_operation()
    return pos


@logwrap
def swipe(v1, v2=None, vector=None, **kwargs):
    """
    Perform the swipe action on the device screen.

    There are two ways of assigning the parameters
        * ``swipe(v1, v2=Template(...))``   # swipe from v1 to v2
        * ``swipe(v1, vector=(x, y))``      # swipe starts at v1 and moves along the vector.


    :param v1: the start point of swipe,
               either a Template instance or absolute coordinates (x, y)
    :param v2: the end point of swipe,
               either a Template instance or absolute coordinates (x, y)
    :param vector: a vector coordinates of swipe action, either absolute coordinates (x, y) or percentage of
                   screen e.g.(0.5, 0.5)
    :param **kwargs: platform specific `kwargs`, please refer to corresponding docs
    :raise Exception: general exception when not enough parameters to perform swap action have been provided
    :return: Origin position and target position
    :platforms: Android, Windows, iOS
    :Example:

        >>> swipe(Template(r"tpl1606814865574.png"), vector=[-0.0316, -0.3311])
        >>> swipe((100, 100), (200, 200))

        Custom swiping duration and number of steps(Android and iOS)::

        >>> # swiping lasts for 1 second, divided into 6 steps
        >>> swipe((100, 100), (200, 200), duration=1, steps=6)

    """
    if isinstance(v1, Template):
        try:
            pos1 = loop_find(v1, timeout=ST.FIND_TIMEOUT)
        except TargetNotFoundError:
            # 如果由图1滑向图2，图1找不到，会导致图2的文件路径未被初始化，可能在报告中不能正确显示
            if v2 and isinstance(v2, Template):
                v2.filepath
            raise
    else:
        try_log_screen()
        pos1 = v1

    if v2:
        if isinstance(v2, Template):
            pos2 = loop_find(v2, timeout=ST.FIND_TIMEOUT_TMP)
        else:
            pos2 = v2
    elif vector:
        if vector[0] <= 1 and vector[1] <= 1:
            w, h = G.DEVICE.get_current_resolution()
            vector = (int(vector[0] * w), int(vector[1] * h))
        pos2 = (pos1[0] + vector[0], pos1[1] + vector[1])
    else:
        raise Exception("no enough params for swipe")

    G.DEVICE.swipe(pos1, pos2, **kwargs)
    delay_after_operation()
    return pos1, pos2


@logwrap
def pinch(in_or_out='in', center=None, percent=0.5):
    """
    Perform the pinch action on the device screen

    :param in_or_out: pinch in or pinch out, enum in ["in", "out"]
    :param center: center of pinch action, default as None which is the center of the screen
    :param percent: percentage of the screen of pinch action, default is 0.5
    :return: None
    :platforms: Android
    :Example:

        Pinch in the center of the screen with two fingers::

        >>> pinch()

        Take (100,100) as the center and slide out with two fingers::

        >>> pinch('out', center=(100, 100))
    """
    try_log_screen()
    G.DEVICE.pinch(in_or_out=in_or_out, center=center, percent=percent)
    delay_after_operation()


@logwrap
def keyevent(keyname, **kwargs):
    """
    Perform key event on the device

    :param keyname: platform specific key name
    :param **kwargs: platform specific `kwargs`, please refer to corresponding docs
    :return: None
    :platforms: Android, Windows, iOS
    :Example:

        * ``Android``: it is equivalent to executing ``adb shell input keyevent KEYNAME`` ::

        >>> keyevent("HOME")
        >>> # The constant corresponding to the home key is 3
        >>> keyevent("3")  # same as keyevent("HOME")
        >>> keyevent("BACK")
        >>> keyevent("KEYCODE_DEL")

        .. seealso::

           Module :py:mod:`airtest.core.android.adb.ADB.keyevent`
              Equivalent to calling the ``android.adb.keyevent()``

           `Android Keyevent <https://developer.android.com/reference/android/view/KeyEvent#constants_1>`_
              Documentation for more ``Android.KeyEvent``

        * ``Windows``: Use ``pywinauto.keyboard`` module for key input::

        >>> keyevent("{DEL}")
        >>> keyevent("%{F4}")  # close an active window with Alt+F4

        .. seealso::

            Module :py:mod:`airtest.core.win.win.Windows.keyevent`

            `pywinauto.keyboard <https://pywinauto.readthedocs.io/en/latest/code/pywinauto.keyboard.html>`_
                Documentation for ``pywinauto.keyboard``

        * ``iOS``: Only supports home/volumeUp/volumeDown::

        >>> keyevent("HOME")
        >>> keyevent("volumeUp")

    """
    G.DEVICE.keyevent(keyname, **kwargs)
    delay_after_operation()


@logwrap
def text(text, enter=True, **kwargs):
    """
    Input text on the target device. Text input widget must be active first.

    :param text: text to input, unicode is supported
    :param enter: input `Enter` keyevent after text input, default is True
    :return: None
    :platforms: Android, Windows, iOS
    :Example:

        >>> text("test")
        >>> text("test", enter=False)

        On Android, sometimes you need to click the search button after typing::

        >>> text("test", search=True)

        .. seealso::

            Module :py:mod:`airtest.core.android.ime.YosemiteIme.code`

            If you want to enter other keys on the keyboard, you can use the interface::

                >>> text("test")
                >>> device().yosemite_ime.code("3")  # 3 = IME_ACTION_SEARCH

            Ref: `Editor Action Code <http://developer.android.com/reference/android/view/inputmethod/EditorInfo.html>`_

    """
    G.DEVICE.text(text, enter=enter, **kwargs)
    delay_after_operation()


@logwrap
def sleep(secs=1.0):
    """
    Set the sleep interval. It will be recorded in the report

    :param secs: seconds to sleep
    :return: None
    :platforms: Android, Windows, iOS
    :Example:

        >>> sleep(1)
    """
    time.sleep(secs)


@logwrap
def wait(v, timeout=None, interval=0.5, intervalfunc=None):
    """
    Wait to match the Template on the device screen

    :param v: target object to wait for, Template instance
    :param timeout: time interval to wait for the match, default is None which is ``ST.FIND_TIMEOUT``
    :param interval: time interval in seconds to attempt to find a match
    :param intervalfunc: called after each unsuccessful attempt to find the corresponding match
    :raise TargetNotFoundError: raised if target is not found after the time limit expired
    :return: coordinates of the matched target
    :platforms: Android, Windows, iOS
    :Example:

        >>> wait(Template(r"tpl1606821804906.png"))  # timeout after ST.FIND_TIMEOUT
        >>> # find Template every 3 seconds, timeout after 120 seconds
        >>> wait(Template(r"tpl1606821804906.png"), timeout=120, interval=3)

        You can specify a callback function every time the search target fails::

        >>> def notfound():
        >>>     print("No target found")
        >>> wait(Template(r"tpl1607510661400.png"), intervalfunc=notfound)

    """
    timeout = timeout or ST.FIND_TIMEOUT
    pos = loop_find(v, timeout=timeout, interval=interval, intervalfunc=intervalfunc)
    return pos


@logwrap
def exists(v):
    """
    Check whether given target exists on device screen

    :param v: target to be checked
    :return: False if target is not found, otherwise returns the coordinates of the target
    :platforms: Android, Windows, iOS
    :Example:

        >>> if exists(Template(r"tpl1606822430589.png")):
        >>>     touch(Template(r"tpl1606822430589.png"))

        Since ``exists()`` will return the coordinates, we can directly click on this return value to reduce one image search::

        >>> pos = exists(Template(r"tpl1606822430589.png"))
        >>> if pos:
        >>>     touch(pos)

    """
    try:
        pos = loop_find(v, timeout=ST.FIND_TIMEOUT_TMP)
    except TargetNotFoundError:
        return False
    else:
        return pos


@logwrap
def find_all(v):
    """
    Find all occurrences of the target on the device screen and return their coordinates

    :param v: target to find
    :return: list of results, [{'result': (x, y),
                                'rectangle': ( (left_top, left_bottom, right_bottom, right_top) ),
                                'confidence': 0.9},
                                ...]
    :platforms: Android, Windows, iOS
    :Example:

        >>> find_all(Template(r"tpl1607511235111.png"))
        [{'result': (218, 468), 'rectangle': ((149, 440), (149, 496), (288, 496), (288, 440)),
        'confidence': 0.9999996423721313}]

    """
    screen = G.DEVICE.snapshot(quality=ST.SNAPSHOT_QUALITY)
    return v.match_all_in(screen)


def _check_image_name_pngFormat(_input_name: str) -> str:
    if '.png' in _input_name:
        return _input_name
    else:
        return _input_name + '.png'


def get_time() -> str:
    return time.strftime("%Y-%m-%d_%H_%M_%S_", time.localtime())


def setup_sub_root(script_object: object)->Dict[str,str]:
    _current_path = script_object.current_path
    try:
        _sub_root_dict = script_object.sub_root_dict
    except Exception as e:
        '''
        _sub_root_dict={
            'tmp_root': 'tmp/',
            'icon_root': 'icon/script_icon_file_name/',
            'save_root': 'storage/script_name/',
            'backup_root': 'backup/script_name/',
        }
        '''
        log(f'setup_sub_root method : sub_root_dict not found, please check your script in follow format \n {_sub_root_dict}',timestamp=time.time())
        
        raise e
    for _key, _value in  _sub_root_dict.items():
        if (_key != 'icon_root'): _sub_root_dict[_key] = script_object.device_num + '/' + _value

    for _key, _document_path in _sub_root_dict.items():
            _document_path_temp =os.path.join(_current_path,_document_path) 
            if not os.path.isdir(_document_path_temp):
                os.makedirs(_document_path_temp)
    log('setup_sub_root method : create sub root successes',timestamp=time.time())
    return _sub_root_dict

def _send_log_to_ui(script_object: object, _log_message: str):
    _ui_label_dict = script_object.pyqt6_ui_label_dict
    _log_message = _log_message.replace(',','\n').replace(':','\n')
    if _ui_label_dict:
        _ui_label_dict['log_label'].setText(_log_message)

def _send_image_path_to_ui(script_object: object, _image_path: str):
    _ui_label_dict = script_object.pyqt6_ui_label_dict
    
    if _ui_label_dict:
        _pyqt_img = cv2.imread(_image_path)
        height, width, channel = _pyqt_img.shape
        bytesPerline = 3 * width
        _qimg = QImage(_pyqt_img, width, height, bytesPerline,
                            QImage.Format.Format_RGB888).rgbSwapped()  #type: ignore
        _ui_label_dict['image_label'].setPixmap(QPixmap.fromImage(_qimg))



def setup_log_file(script_object: object)->None:
    __author__ = "Airtest"
    import logging
    logger = logging.getLogger("airtest")
    logger.setLevel(logging.INFO)
    _current_path = script_object.current_path
    _sub_root_dict = script_object.sub_root_dict
    _script_name = script_object.script_name
    _log_file_path = os.path.join(_current_path,_sub_root_dict['log_root'])

    _log_file_name = get_time()+ f'{_script_name}.txt'
    _log_file_path = os.path.join(_log_file_path, _log_file_name)
    
    fh = logging.FileHandler(_log_file_path, encoding='utf-8')
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
            '%(levelname)-6s[%(asctime)s]:%(threadName)s: %(message)s ',
            datefmt="%H:%M:%S",
        ))
    logger.addHandler(fh)
    logger.info('set log path:'+_log_file_path)
    


@logwrap
def check_image_recognition(
    script_object: object,
    template_image_name: str,
    compare_times_counter: int = 1,
    screenshot_wait_time: float = 0.1,
    accuracy_val: float = 0.9,
    is_refresh_screenshot: bool = True,
    screen_image_name: str = 'tmp0',
    screen_image_root_dict_key: str = 'tmp_root',
    screen_image_additional_root: str = '',
    template_image_root_dict_key: str = 'icon_root',
    template_image_additional_root: str = '',
    repeatedly_screenshot_times: int = 1,
):
    def _false_log(__result)->None: #need improve
        if __result != None:
            _best_result = sorted(__result, key=lambda d: d['confidence'])
            _log_message = "check_image_recognition method : template_name= {}, prob= {:.4f}, accuracy_val= {:.4f}, result= {}".format(
                template_image_name, _best_result[-1]['confidence'], accuracy_val, False)
            log(_log_message,timestamp=time.time())
            _send_log_to_ui(script_object, _log_message)
            _send_image_path_to_ui(script_object,template_image_name)
            _back_up_image(_screen,_result[-1]['confidence'],False)
        else:
            _log_message="check_image_recognition method : template_name= {} prob= below 0.6 accuracy_val= {:.4f} result= {}".format(
                template_image_name, accuracy_val, False)
            log(_log_message,timestamp=time.time())
            _send_log_to_ui(script_object, _log_message)
            _send_image_path_to_ui(script_object,template_image_name)
            _back_up_image(_screen,'below_0.6',False)
    def _back_up_image(__screen,__confidence,__result) -> None:   
        if _is_backup_image :
            __back_up_image_path = os.path.join(_current_path, _sub_root_dict['backup_root'], _check_image_name_pngFormat(f'{get_time()}{template_image_name}_{__confidence}_{__result}'))
            Image.fromarray(cv2.cvtColor(__screen, cv2.COLOR_RGB2BGR)).save(__back_up_image_path)
    _current_path = script_object.current_path
    _sub_root_dict = script_object.sub_root_dict
    _is_backup_image = script_object.is_backup_image
    _screen_image_path = os.path.join(_current_path, _sub_root_dict[screen_image_root_dict_key], screen_image_additional_root,
                                      _check_image_name_pngFormat(screen_image_name))
    _template_image_path = os.path.join(_current_path, _sub_root_dict[template_image_root_dict_key],
                                        template_image_additional_root, _check_image_name_pngFormat(template_image_name))

    if repeatedly_screenshot_times == 1:
        for _num in range(compare_times_counter):
            if is_refresh_screenshot:
                time.sleep(screenshot_wait_time)
                _screen = G.DEVICE.snapshot(filename=_screen_image_path, quality=ST.SNAPSHOT_QUALITY)
            else:
                _screen = cv2.imread(_screen_image_path)
            _template = Template(filename=_template_image_path, record_pos=(0.5, 0.5), threshold=LOWEST_THRESHOLD)
            _result = _template.match_all_in(_screen)
            if _result != None:
                _best_result = sorted(_result, key=lambda d: d['confidence'])
                if _best_result[-1]['confidence'] > accuracy_val:
                    _log_message = "check_image_recognition method : template_name= {}, prob= {:.4f}, accuracy_val= {:.4f}, result= {}".format(template_image_name, _best_result[-1]['confidence'], accuracy_val, True)
                    log(_log_message,timestamp=time.time())
                    _send_log_to_ui(script_object, _log_message)
                    _send_image_path_to_ui(script_object,_template_image_path)
                    _back_up_image(_screen,_best_result[-1]['confidence'],True)
                    return _best_result
        _false_log(_result)
        return False
    else:
        _screen_image_name_list = [f'tmp{x}' for x in range(repeatedly_screenshot_times)]
        time.sleep(screenshot_wait_time)
        for _num in range(compare_times_counter):
            _screen_list = []
            for _tmp_screen_image_name in _screen_image_name_list:
                _screen_list.append(
                    G.DEVICE.snapshot(filename=os.path.join(_current_path, _sub_root_dict[screen_image_root_dict_key],
                                                            screen_image_additional_root,
                                                            _check_image_name_pngFormat(_tmp_screen_image_name)),
                                      quality=ST.SNAPSHOT_QUALITY))

            _template = Template(_template_image_path,
                                 record_pos=(0.5, 0.5),
                                 threshold=LOWEST_THRESHOLD)

            for _screen in _screen_list:
                _result = _template.match_all_in(_screen)
                if _result != None:
                    _best_result = sorted(_result, key=lambda d: d['confidence'])
                    if _best_result[-1]['confidence'] > accuracy_val:
                        log("check_image_recognition method : template_name= {} prob= {:.4f} accuracy_val= {:.4f} result= {}".
                            format(template_image_name, _best_result[-1]['confidence'], accuracy_val, True),
                            timestamp=time.time())
                        _back_up_image(_screen,_best_result[-1]['confidence'],True)
                        return _best_result
        _false_log(_result)
        return False


def adb_default_tap(
    script_object: object,
    template_image_name: str,
    compare_times_counter: int = 1,
    screenshot_wait_time: float = 0.1,
    tap_execute_wait_time: float = 0.1,
    accuracy_val: float = 0.9,
    is_refresh_screenshot: bool = True,
    tap_execute_counter_times: int = 1,
    tap_offset: Tuple[int, int] = (0, 0),
    screen_image_name: str = 'tmp0',
    screen_image_root_dict_key: str = 'tmp_root',
    screen_image_additional_root: str = '',
    template_image_root_dict_key: str = 'icon_root',
    template_image_additional_root: str = '',
    repeatedly_screenshot_times: int = 1,
) -> bool:
    """_summary_ compare device screen with specify image,if image is similar,excute tap fuction and return true ,else return false

        Args:
            png_name (str): _description_
            offset (Tuple[int, int], optional): _description_. Defaults to (0,0).
            wait_time (float, optional): wait time. Defaults to 1.
            tap_wait_time (float, optional): _description_. Defaults to 0.
            tap_times (int, optional): _description_. Defaults to 1.

        Returns:
            bool: _description_
        """

    _result = check_image_recognition(
        script_object,
        template_image_name,
        compare_times_counter,
        screenshot_wait_time,
        accuracy_val,
        is_refresh_screenshot,
        screen_image_name,
        screen_image_root_dict_key,
        screen_image_additional_root,
        template_image_root_dict_key,
        template_image_additional_root,
        repeatedly_screenshot_times,
    )

    if _result != False:
        _pos = _result[-1]['result']
        (_x, _y) = map(sum, zip(_pos, tap_offset))
        for _num in range(tap_execute_counter_times):
            time.sleep(tap_execute_wait_time)
            click((_x, _y))
        log("adb_default_tap method : template_name= {} tap_pos= {} tap_offset= {} result= {}".format(
            template_image_name, _pos, tap_offset, True),
            timestamp=time.time())
        return True
    else:
        log("adb_default_tap method : template_name= {} result= {}".format(template_image_name, False), timestamp=time.time())
        return False


def adb_default_swipe(
    script_object: object,
    template_image_name: str,
    swipe_offset_position: Tuple[int, int] = (0, 0),
    swiping_time: float = 0.3,
    screenshot_wait_time: float = 0.1,
    compare_times_counter: int = 1,
    accuracy_val: float = 0.9,
    is_refresh_screenshot: bool = True,
    swipe_execute_counter_times: int = 1,
    swipe_execute_wait_time: float = 0,
    screen_image_name: str = 'tmp0',
    screen_image_root_dict_key: str = 'tmp_root',
    screen_image_additional_root: str = '',
    template_image_root_dict_key: str = 'icon_root',
    template_image_additional_root: str = '',
    repeatedly_screenshot_times: int = 1,
) -> bool:
    """_summary_ compare device screen with specify image,if image is similar,excute swipe fuction and return true ,else return false

        Args:
            png_name (str): _description_
            offset_position (Tuple[int, int], optional): _description_. Defaults to (0,0).
            swipe_time (int, optional): set swipe fast or swipe slow. Defaults to 0.
            wait_time (int, optional): wait time. Defaults to 1.

        Returns:
            bool: if image is similar,excute swipe fuction and return true ,else return false
        """

    #itp is accuracy between png_name and screenshot ,if > 0.9 return position else return false
    _result = check_image_recognition(
        script_object,
        template_image_name,
        compare_times_counter,
        screenshot_wait_time,
        accuracy_val,
        is_refresh_screenshot,
        screen_image_name,
        screen_image_root_dict_key,
        screen_image_additional_root,
        template_image_root_dict_key,
        template_image_additional_root,
        repeatedly_screenshot_times,
    )

    if _result != False:
        _pos = _result[-1]['result']
        (_x, _y) = map(sum, zip(_pos, swipe_offset_position))
        for _num in range(swipe_execute_counter_times):
            time.sleep(swipe_execute_wait_time)
            swipe(_pos, (_x, _y), duration=swiping_time)
        log("adb_default_swipe method : template_name= {} swipe_pos= {} swipe_offset_position= {} result= {}".format(
            template_image_name, _pos, swipe_offset_position, True),
            timestamp=time.time())
        return True
    else:
        log("adb_default_swipe method : template_name= {} result= {}".format(template_image_name, False), timestamp=time.time())
        return False


def adb_default_press(
    script_object: object,
    template_image_name: str,
    pressing_time: float = 0.3,
    screenshot_wait_time: float = 0.1,
    compare_times_counter: int = 1,
    accuracy_val: float = 0.9,
    is_refresh_screenshot: bool = True,
    press_execute_counter_times: int = 1,
    press_execute_wait_time: float = 0,
    screen_image_name: str = 'tmp0',
    screen_image_root_dict_key: str = 'tmp_root',
    screen_image_additional_root: str = '',
    template_image_root_dict_key: str = 'icon_root',
    template_image_additional_root: str = '',
    repeatedly_screenshot_times: int = 1,
) -> bool:
    _result = check_image_recognition(
        script_object,
        template_image_name,
        compare_times_counter,
        screenshot_wait_time,
        accuracy_val,
        is_refresh_screenshot,
        screen_image_name,
        screen_image_root_dict_key,
        screen_image_additional_root,
        template_image_root_dict_key,
        template_image_additional_root,
        repeatedly_screenshot_times,
    )

    if _result != False:
        _pos = _result[-1]['result']
        for _num in range(press_execute_counter_times):
            time.sleep(press_execute_wait_time)
            swipe(_pos, _pos, duration=pressing_time)
        log("adb_default_swipe method : template_name= {} swipe_pos= {} result= {}".format(template_image_name, _pos, True),
            timestamp=time.time())
        return True
    else:
        log("adb_default_swipe method : template_name= {} result= {}".format(template_image_name, False), timestamp=time.time())
        return False


@logwrap
def save_screenshot_compression(script_object: object,
                                save_image_name: str = '',
                                load_image_root_dict_key: str = 'tmp_root',
                                save_image_root_dict_key: str = 'save_root',
                                screenshot_wait_time: float = 0.1,
                                compression: float = 1,
                                load_image_name: str = 'tmp0.png',
                                save_image_additional_root: str = '',
                                is_save_image_name_add_time: bool = False,
                                is_refresh_screenshot: bool = True) -> None:
    """_summary_ save image to specify root, this root need to be create, image can be compreess by setting variable compression 0~1 (0~100%) 

        Args:
            save_sub_root (str, optional): _description_. Defaults to ''.
            save_name (str, optional): _description_. Defaults to ''.
            wait_time (float, optional): _description_. Defaults to 1.
            compression (float, optional): image can be compreess by setting variable compression 0~1 (0~100%). Defaults to 1.
        """
    _current_path = script_object.current_path
    _sub_root_dict = script_object.sub_root_dict
    _save_image_name = _check_image_name_pngFormat(save_image_name)
    _load_image_name = _check_image_name_pngFormat(load_image_name)

    if is_save_image_name_add_time:
        _save_image_name = get_time() + _save_image_name

    _load_image_path = os.path.join(_current_path, _sub_root_dict[load_image_root_dict_key], _load_image_name)
    _save_image_path = os.path.join(_current_path, _sub_root_dict[save_image_root_dict_key], save_image_additional_root,
                                    _save_image_name)

    if is_refresh_screenshot:
        time.sleep(screenshot_wait_time)
        _screen = G.DEVICE.snapshot(filename=_load_image_path, quality=ST.SNAPSHOT_QUALITY)

    _raw_img = Image.open(_load_image_path)

    if (compression != 1):
        (_width, _height) = _raw_img.size
        #print('原始像素'+'w=%d, h=%d', w, h)
        _width = int(_width * compression)
        _height = int(_height * compression)
        _resized_img = _raw_img.resize((_width, _height))
        _resized_img.save(_save_image_path)
        log(f"save_screenshot_compression method : _raw_img w={_width }, h={_height } compression = {compression} save_name={_save_image_name} "
            )
    else:
        (_width, _height) = _raw_img.size
        _raw_img.save(_save_image_path)
        log(f"save_screenshot_compression method : _raw_img w={_width }, h={_height } save_name={_save_image_name}")


def crop_screenshot(script_object: object,
                    save_image_name: str,
                    save_image_root_dict_key: str,
                    upper_left_coordinate: Tuple[int, int],
                    lower_right_coordinate: Tuple[int, int],
                    load_image_root_dict_key: str = 'tmp_root',
                    load_image_name: str = 'tmp0.png',
                    save_image_additional_root: str = '',
                    screenshot_wait_time: float = 0.1,
                    is_refresh_screenshot: bool = False,
                    is_save_image_name_add_time: bool = False) -> None:
    """_summary_

        Args:
            load_sub_root (str): _description_
            pos_x (int): _description_
            pos_y (int): _description_
            pos_x2 (int): _description_
            pos_y2 (int): _description_
            save_name (str): _description_
            save_sub_root (str): _description_
        """
    _current_path = script_object.current_path
    _sub_root_dict = script_object.sub_root_dict
    _save_image_name = _check_image_name_pngFormat(save_image_name)
    _load_image_name = _check_image_name_pngFormat(load_image_name)

    if is_save_image_name_add_time:
        _save_image_name = get_time() + _save_image_name

    _load_image_path = os.path.join(_current_path, _sub_root_dict[load_image_root_dict_key], _load_image_name)
    _save_image_path = os.path.join(_current_path, _sub_root_dict[save_image_root_dict_key], save_image_additional_root,
                                    _save_image_name)

    if is_refresh_screenshot:
        time.sleep(screenshot_wait_time)
        _screen = G.DEVICE.snapshot(filename=_load_image_path, quality=ST.SNAPSHOT_QUALITY)

    _raw_img = Image.open(_load_image_path)
    (_width, _height) = _raw_img.size
    _pos_x, _pos_y = upper_left_coordinate
    _pos_x2, _pos_y2 = lower_right_coordinate

    _pos_x2 -= _pos_x
    _pos_y2 -= _pos_y
    _region = (_pos_x, _pos_y, _pos_x + _pos_x2, _pos_y + _pos_y2)
    _cropped_img = _raw_img.crop(_region)
    (_cropped_img_width, _cropped_img_height) = _cropped_img.size
    _cropped_img.save(_save_image_path)
    log(f"crop_screenshot method : _raw_img w= {_width } h={_height } cropped_img w= {_cropped_img_width } h= {_cropped_img_height } pos= {upper_left_coordinate},{lower_right_coordinate} save_name= {_save_image_name}"
        )


"""
Assertions: see airtest/core/assertions.py
"""

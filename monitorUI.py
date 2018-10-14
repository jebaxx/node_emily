#!/usr/bin/python
# -*- coding: utf-8 -*-
#
import sys
import logging
import time
import RPi.GPIO as GPIO
import smbus
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
from shutil import copyfile

__i2c = None

###############
## OBJ DUMP
##
from pprint import pformat
import types

def var_dump(obj):
    return pformat(dump(obj))

def dump(obj):
    '''return a printable representation of an object for debugging'''
    newobj = obj
    if isinstance(obj, list):
	# LIST
	newobj = []
	for item in obj:
	    newobj.append(dump(item))
    elif isinstance(obj, tuple):
	# TUPLE
	temp = []
	for item in obj:
	    temp.append(dump(item))
	newobj = tuple(temp)
    elif isinstance(obj, set):
	# SET
	temp = []
	for item in obj:
	    # DICTIONARY TO STRING
	    temp.append(str(dump(item)))
	newobj = set(temp)
    elif isinstance(obj, dict):
	# DICTIONARY
	newobj = {}
	for key, value in obj.items():
	    # DICTIONARY TO STRING
	    newobj[str(dump(key))] = dump(value)
    elif isinstance(obj, types.FunctionType):
	# FUNCTION
	newobj = repr(obj)
    elif '__dict__' in dir(obj):
	# NEW CLASS
	newobj = obj.__dict__.copy()
	if ' object at ' in str(obj) and not '__type__' in newobj:
	    newobj['__type__']=str(obj).replace(" object at ", " #").replace("__main__.", "")
	for attr in newobj:
	    newobj[attr]=dump(newobj[attr])
    return newobj

######################################################################
#  Sub process (cooperate with monitorBase)
#
#	manage LED display and button devices
#====================================================================#

################################################
# LED display library

class ld():

    i2cAddr_LD = 0x3c	# SO1602 LED display I2C Address
    _i2c = None

    #---------------------------------------------------------------------------------
    N   = 8		# 1   # 1: 2/4-line mode  0: 1/3-line mode
    DH  = 4		# 0/1 # Double height font control for 2-line mode
    RE  = 2		# ... # RE flag
    IS  = 1		# ... # IS flag
    BE  = 4		# 0   # CGRAM blink 1: Enable  0: Disable
    REV = 1		# 0   # 1: Reverse display  0: Normal display

    FW  = 4		# 0   # 1: 6-dot font  0: 5-dot font
    BW  = 2		# 0   # inverting cursor  1: Enable 0: disable
    NW  = 1		# 0   # 1: 3 or 4 line  0: 1 or 2 line
    #---------------------------------------------------------------------------------
    UD2 = 8		# 1   # Double height format (should be 1 )
    UD1 = 4		# 1   # Double height format (should be 1 )
    DHD = 1		# 0/1 # 1: display shift enable  0: dot scroll enable

    S   = 1		# display shift enable

    SC  = 8		# 1: Scroll  0: cursor shift
    RL  = 4		# Scroll(shift) direction 1: right  0: left
    #---------------------------------------------------------------------------------
    led    = 4		# display On/Off
    cursor = 2		# cursor On/Off
    blink  = 1		# cursor blink sw
    #---------------------------------------------------------------------------------

    # # INTERNAL methods # #

    @staticmethod
    def ms_delay(n):
	time.sleep(n / 1000000.0)

    @staticmethod
    def so_cmd(c) :
	ld._i2c.write_byte_data(ld.i2cAddr_LD, 0, c)
	ld.ms_delay(5)

    @staticmethod
    def set_Line_mode_1_2() :
        
	ld.so_cmd(0x20 | (ld.N  & ld.N) | (ld.BE & 0) | (ld.RE & ld.RE) | (ld.REV & 0))	# RE = 1 , N = 1 : 2 or 4 line
	ld.so_cmd(0x08 | (ld.FW & 0) | (ld.BW & 0) | (ld.NW & 0))		        # NW = 0 :  1 or 2 line
	ld.so_cmd(0x20 | (ld.N  & ld.N) | (ld.DH)     | (ld.RE &  0) | (ld.IS &  0))	# RE = 0 , n = 1 : 2 or 4 line

    @staticmethod
    def init_1602() :

	ld.DH  = 0
	ld.DHD = 1
	ld.set_Line_mode_1_2()
	ld.clear_display()
	ld.ms_delay(20)
	ld.return_to_home()
	ld.display_sw(1)
	ld.return_to_home()
	ld.ms_delay(20)

    # # PUBLIC METHODS # #

    @staticmethod
    def init(i2c):
	ld._i2c = i2c
	ld.init_1602()
	ld.set_contrast(0x38)
	ld.clear_display()

    @staticmethod
    def clear_display() :
	ld.so_cmd(0x01)

    @staticmethod
    def return_to_home():
	ld.so_cmd(2)

    @staticmethod
    def display_sw(sw):
	ld.led    = (sw & 1)     << 2
	cmd = 8 | ld.led | ld.cursor | ld.blink
	ld.so_cmd(cmd)

    @staticmethod
    def cursor_sw(sw):
	if sw & 1: 
	    ld.curosr = 2
	    ld.blink  = 1
	else :
	    ld.cursor = 0
	    ld.blink = 0
	cmd = 8 | ld.led | ld.cursor | ld.blink
	ld.so_cmd(cmd)

    @staticmethod
    def set_double_height(sw):
	if sw == 0:	ld.DH = 0
	else:		ld.DH = 4
	ld.so_cmd(0x20 | (ld.N  & ld.N) | (ld.DH)     | (ld.RE &  0) | (ld.IS &  0))	# RE = 0 , n = 1 : 2 or 4 line

    @staticmethod
    def set_contrast(c) :

	ld.so_cmd(0x20 | (ld.N  & ld.N) | (ld.BE & 0) | (ld.RE & ld.RE) | (ld.REV & 0))		# RE = 1
	ld.so_cmd(0x79)										# SD = 1
	ld.so_cmd(0x81)										# set contrast
	ld.so_cmd(c)										# value
	ld.so_cmd(0x78)										# SD = 0
	ld.so_cmd(0x20 | (ld.N  & ld.N) | (ld.DH)     | (ld.RE &  0) | (ld.IS & 0))		# RE = 0

    @staticmethod
    def set_location(l, c):
	c = c + 0x80        # 1st line is start with 0x80
	if l == 1:
	    c = c + 0x40    # 2nd line is start with 0xc0
        
	ld.so_cmd(c)

    @staticmethod
    def write_char(str, l = None, c = None):
        
	if (c != None) :
	    ld.set_location(l, c)

	ld._i2c.write_i2c_block_data(ld.i2cAddr_LD, 0x40, map(ord, str))

######################################################################
#  display manager class

class d_m():

    _i2c = None
    _state = ""
    _states = [ 'config', 'clock', 'sensor' , 'alarm' ]

    I2CADDR_BTN  = 0x3f  # button shim I2C Address
    _key_state   = 0
    _current_mode = '0'		# current hsd_mode

    REG_INPUT    = 0x00
    REG_OUTPUT   = 0x01
    REG_POLARITY = 0x02
    REG_CONFIG   = 0x03

    NUM_BUTTONS = 5

    _clock_form = [	'%m/%d %H:%M %a',
			' %m/%d %H:%M %a',
			'%m/%d %H:%M',
			'  %m/%d %H:%M',
			'    %m/%d %H:%M',
			'%H:%M  %a',
			'  %H:%M  %a',
			'    %H:%M %a',
			'      %H:%M %a',
			'        %H:%M',
			'          %H:%M' ]

    _sens_form = [	'{temp:05.2f}C   {hum:04.1f}%' ,
			' {temp:05.2f}C   {hum:04.1f}%' ,
			'  {temp:05.2f}C  {hum:04.1f}%' ]


    @staticmethod
    def init(__i2c) :
	logger = logging.getLogger(__name__)
	d_m._i2c = __i2c
	d_m._state = c_m.get('initial_dm_state')
	GPIO.setmode( GPIO.BCM )
	GPIO.setup( 27, GPIO.IN )
	GPIO.add_event_detect( 27, GPIO.FALLING, callback = d_m.button_callback )
	ld.init(__i2c)
	d_m._current_mode = str(c_m.get('hsd_mode'))
	if d_m._state == 'clock' or d_m._state == 'sensor' : d_m.redraw_display()
	elif d_m._state == 'config' : c_m.redraw_display()
	elif d_m._state == 'alarm' : al_a.redraw_display()

    #
    #  set configuration
    #
    @staticmethod
    def set_state(new_state) :
	d_m._state = new_state

    #
    #   expected to be called periodically
    #
    @staticmethod
    def polling() :
	pass

    #
    #  button_callback
    #
    #   get button state(whitch button has been pushed)
    #
    @staticmethod
    def button_callback(portNo):
        
	logger = logging.getLogger(__name__)
	key_state = d_m._i2c.read_byte_data(d_m.I2CADDR_BTN, d_m.REG_INPUT)
	key_state = ~key_state & 0b011111
#	logger.debug("key_detect:" + str(key_state))

	if (key_state & 0b000001) > 0 :
	    #
	    # change _state
	    #
	    d_m.change_state()

	if key_state & 0b011110 :
	    if d_m._state == 'clock' or d_m._state == 'sensor' :
		d_m.key_event(key_state)
	    elif d_m._state == 'config':
		c_m.key_event(key_state)
	    elif d_m._state == 'alarm':
		al_a.key_event(key_state)

    #
    #  Change d_m_status
    #
    @staticmethod
    def change_state():

	logger = logging.getLogger(__name__)

	if d_m._state == 'config': 
	    # the case of exit from 'config', it's needed to check changed items and treat them.
	    c_m.check_modified_items()

	i = d_m._states.index(d_m._state) + 1
	if i == len(d_m._states): i = 0
	d_m._state = d_m._states[i]
	logger.debug("change_state:next_state="+d_m._state)

	ld.clear_display()

	if d_m._state == 'config':
	    d_m.disable_hsd()
	    c_m.redraw_display()
	elif d_m._state == 'alarm':
	    d_m.disable_hsd()
	    al_a.redraw_display()
	else:	# 'sensor' or 'alarm'
	    d_m.enable_hsd()
	    d_m.redraw_display()


    #
    #  key event handler
    #
    @staticmethod
    def key_event(key_state) :

	logger = logging.getLogger(__name__)
	if d_m._state == 'clock':
	    if key_state & 0b001010 :
		c_m._c['clock_style']['value'] += 1
		if c_m._c['clock_style']['value'] == len(d_m._clock_form): c_m._c['clock_style']['value'] = 0
	    elif key_state & 0b010100 :
		c_m._c['clock_style']['value'] -= 1
		if c_m._c['clock_style']['value'] == -1: c_m._c['clock_style']['value'] = len(d_m._clock_form) - 1

	    ld.clear_display()
	    d_m.redraw_display()

	elif d_m._state == 'sensor':
	    if key_state & 0b000010 :
		c_m._c['sens_style']['clock']['value'] += 1
		if c_m._c['sens_style']['clock']['value'] == len(d_m._clock_form)+1 : c_m._c['sens_style']['clock']['value'] = 0
	    elif key_state & 0b000100 :
		c_m._c['sens_style']['clock']['value'] -= 1
		if c_m._c['sens_style']['clock']['value'] == -1 : c_m._c['sens_style']['clock']['value'] = len(d_m._clock_form)
	    elif key_state & 0b001000 :
		c_m._c['sens_style']['sens']['value'] += 1
		if c_m._c['sens_style']['sens']['value'] == len(d_m._sens_form) : c_m._c['sens_style']['sens']['value'] = 0
	    elif key_state & 0b010000 :
		c_m._c['sens_style']['sens']['value'] -= 1
		if c_m._c['sens_style']['sens']['value'] == -1 : c_m._c['sens_style']['sens']['value'] = len(d_m._sens_form) - 1

	    d_m.redraw_display()

    #
    #  redraw display
    #
    @staticmethod
    def redraw_display():

	logger = logging.getLogger(__name__)
	ld.clear_display()
	ld.cursor_sw(0)
	if d_m._state == 'clock' or c_m._c['sens_style']['clock']['value'] == 0 : ld.set_double_height(1)
	else			: ld.set_double_height(0)

	d_m.refresh_display()

    @staticmethod
    def read_sens_data():
	logger = logging.getLogger(__name__)

	try:
	    with open('/tmp/sens_data.txt', 'r') as f:
		return [float(d) for d in f.read().split(',')]
	except:
	    logger.info("read_sens_data: retrying")
	    time.sleep(0.5)
	    try:
		with open('/tmp/sens_data.txt', 'r') as f:
		    return [float(d) for d in f.read().split(',')]
	    except:
		copyfile('/tmp/sens_data.txt', '/tmp/sens_data_err.txt')
		raise

    #
    #  (periodical) refresh display
    #
    @staticmethod
    def refresh_display():

	logger = logging.getLogger(__name__)
	if d_m._state == 'clock':
	    ld.write_char(datetime.now().strftime(d_m._clock_form[c_m._c['clock_style']['value']]), 0, 0)
	elif d_m._state == 'sensor':
	    temp, temp_c, hum = d_m.read_sens_data()
	    if c_m._c['sens_style']['clock']['value'] != 0 :
		ld.write_char(datetime.now().strftime(d_m._clock_form[c_m._c['sens_style']['clock']['value']-1]), 0, 0)
		ld.write_char(d_m._sens_form[c_m._c['sens_style']['sens']['value']].format(temp=temp, hum=hum), 1, 0)
	    else :
		ld.write_char(d_m._sens_form[c_m._c['sens_style']['sens']['value']].format(temp=temp, hum=hum), 0, 0)
	elif d_m._state == 'config':
	    c_m.refresh_display()
	elif d_m._state == 'alarm':
	    al_a.refresh_display()
	else:
	    ld.write_char('unknown', 0, 0)

    #
    # (temporary) disable & resume hsd mode
    #
    @staticmethod
    def disable_hsd():
	logger = logging.getLogger(__name__)
	logger.debug("disable_hsd")
	d_m._current_mode = '0'
	try:
	    with open('/tmp/pipe', 'w') as f:
	        f.write(d_m._current_mode)
	except EnvironmentError:
	    logger.error("pipe cannot open")

    @staticmethod
    def enable_hsd():
	logger = logging.getLogger(__name__)
	logger.debug("enable_hsd")
	if c_m.get('hsd_mode') == 1:
	    d_m._current_mode = '1'
	    try:
		with open('/tmp/pipe', 'w') as f:
		    f.write(d_m._current_mode)
	    except EnvironmentError:
		logger.error("pipe cannot open")
	else:
	    logger.debug("-- stay disable")

    @staticmethod
    def resume_hsd():
	logger = logging.getLogger(__name__)
	logger.debug("resume_hsd")
	try:
	    with open('/tmp/pipe', 'w') as f:
	        f.write(d_m._current_mode)
	except EnvironmentError:
	    logger.error("pipe cannot open")


######################################################################
#  config manager class
import copy

class c_m:
        
    _b = OrderedDict()
    _b['initial_dm_state'] = { 'value':'sensor', 'candidate':('clock', 'sensor', 'alarm', 'config') }
    _b['hsd_mode'] = { 'value':1 , 'range':( 0, 1 ) }
    _b['clock_style'] = { 'value':6 , 'range':( 0, 10 ) }

    _b['sens_style'] = OrderedDict()
    _b['sens_style']['sens'] = { 'value':0, 'range':( 0, 3 ) } 
    _b['sens_style']['clock'] = { 'value':7, 'range':( 0, 10) } 

    _b['alarm'] =  OrderedDict()
    _b['alarm']['alarm1'] = OrderedDict()
    _b['alarm']['alarm1']['sw '] = { 'value':'OFF', 'candidate':( 'ON', 'OFF' ) }
    _b['alarm']['alarm1']['wek'] = { 'value':'wek', 'candidate':( 'mon', 'tue', 'wed', 'thr', 'fri', 'sat', 'sun', 'wek', 'hol') }
    _b['alarm']['alarm1']['h '] = { 'value':6, 'range':( 0, 23 ) }
    _b['alarm']['alarm1']['m '] = { 'value':45, 'range':( 0, 59 ) }

    _b['alarm']['alarm2'] = OrderedDict()
    _b['alarm']['alarm2']['sw '] = { 'value':'OFF', 'candidate':( 'ON', 'OFF' ) }
    _b['alarm']['alarm2']['wek'] = { 'value':'wek', 'candidate':( 'mon', 'tue', 'wed', 'thr', 'fri', 'sat', 'sun', 'wek', 'hol') }
    _b['alarm']['alarm2']['h '] = { 'value':7, 'range':( 0, 23 ) }
    _b['alarm']['alarm2']['m '] = { 'value':30, 'range':( 0, 59 ) }

    _b['alarm']['alarm3'] = OrderedDict()
    _b['alarm']['alarm3']['sw '] = { 'value':'OFF', 'candidate':( 'ON', 'OFF' ) }
    _b['alarm']['alarm3']['wek'] = { 'value':'wek', 'candidate':( 'mon', 'tue', 'wed', 'thr', 'fri', 'sat', 'sun', 'wek', 'hol') }
    _b['alarm']['alarm3']['h '] = { 'value':5, 'range':( 0, 23 ) }
    _b['alarm']['alarm3']['m '] = { 'value':50, 'range':( 0, 59 ) }

    _b['reset_settings'] = { 'value':'OFF' , 'candidate':( 'ON', 'OFF' ) }

    _c = {}

    _iter0 = None
    _iter1 = None
    _iter2 = None
    _vy0 = None
    _vy1 = None
    _vy2 = None
    _sublevel = False

    _cand = None
    _range = None

    @staticmethod
    def init():
	c_m._c = copy.deepcopy(c_m._b)

    @staticmethod
    def get(conf_name):
	return c_m._c[conf_name]['value']

    #
    # Traverse the config items of each level (lv0, lv1, lv2)
    #
    @staticmethod
    def rotate_vy0():
	if c_m._vy0 == None: c_m._iter0 = iter(c_m._c.keys())

	try:
	    c_m._vy0 = next(c_m._iter0)
	except StopIteration:
	    c_m._iter0 = iter(c_m._c.keys())
	    c_m._vy0 = next(c_m._iter0)

	c_m._vy1 = None
	c_m._vy2 = None
	c_m._range = c_m._c[c_m._vy0].get('range')
	c_m._cand  = c_m._c[c_m._vy0].get('candidate')
	c_m._sublevel = not ('value' in c_m._c[c_m._vy0]) 

    @staticmethod
    def rotate_vy1():
	if c_m._vy1 == None: c_m._iter1 = iter(c_m._c[c_m._vy0].keys())

	try:
	    c_m._vy1 = next(c_m._iter1)
	except StopIteration:
	    c_m._iter1 = iter(c_m._c[c_m._vy0].keys())
	    c_m._vy1 = next(c_m._iter1)

	c_m._vy2 = None
	c_m._range = c_m._c[c_m._vy0][c_m._vy1].get('range')
	c_m._cand  = c_m._c[c_m._vy0][c_m._vy1].get('candidate')
	c_m._sublevel = not ('value' in c_m._c[c_m._vy0][c_m._vy1]) 

    @staticmethod
    def rotate_vy2():
	if c_m._vy2 == None: c_m._iter2 = iter(c_m._c[c_m._vy0][c_m._vy1].keys())

	try:
	    c_m._vy2 = next(c_m._iter2)
	except StopIteration:
	    c_m._iter2 = iter(c_m._c[c_m._vy0][c_m._vy1].keys())
	    c_m._vy2 = next(c_m._iter2)

	c_m._range = c_m._c[c_m._vy0][c_m._vy1][c_m._vy2].get('range')
	c_m._cand  = c_m._c[c_m._vy0][c_m._vy1][c_m._vy2].get('candidate')
	c_m._sublevel = not ('value' in c_m._c[c_m._vy0][c_m._vy1][c_m._vy2]) 

    @staticmethod
    def rotate_val_in_range(obj):
	obj['value'] += 1
	if obj['value'] > c_m._range[1]:
	   obj['value'] = c_m._range[0]

    @staticmethod
    def rotate_val_from_cand(obj):
	idx = c_m._cand.index(obj['value']) + 1
	if idx >= len(c_m._cand) : idx = 0
        obj['value'] = c_m._cand[idx]
        

    @staticmethod
    def key_event(key_state):
	logger = logging.getLogger(__name__)

	logger.debug("key_event:" + str(key_state) + " ******")
	logger.debug("0: {} - {} - {} sublevel={}".format(c_m._vy0,c_m._vy1,c_m._vy2,c_m._sublevel))

	if key_state & 0b000010 :
	    logger.debug("shift level_vy0 item")
	    c_m.rotate_vy0()

	elif key_state & 0b000100 :
	    if c_m._vy1 is not None or (c_m._vy1 is None and c_m._sublevel):
		logger.debug("shift level_vy1 item")
		c_m.rotate_vy1()

	    elif c_m._vy1 is None and not c_m._sublevel:
		logger.debug("change the value of level_vy0")

		if c_m._range is not None:
		    c_m.rotate_val_in_range(c_m._c[c_m._vy0])
		if c_m._cand is not None:
		    c_m.rotate_val_from_cand(c_m._c[c_m._vy0])
		c_m._c[c_m._vy0]['mod'] = 1
	    else: return

	elif key_state & 0b001000 :
	    if c_m._vy2 is not None or (c_m._vy1 is not None and c_m._sublevel):
		logger.debug("shift level2 item")
		c_m.rotate_vy2()

	    elif c_m._vy1 is not None and not c_m._sublevel:
		logger.debug("change the value of level_vy1")

		if c_m._range is not None:
		    c_m.rotate_val_in_range(c_m._c[c_m._vy0][c_m._vy1])
		if c_m._cand is not None:
		    c_m.rotate_val_from_cand(c_m._c[c_m._vy0][c_m._vy1])
		c_m._c[c_m._vy0][c_m._vy1]['mod'] = 1
	    else: return

	elif key_state & 0b010000:
	    if c_m._vy2 is not None and not c_m._sublevel:
		logger.debug("change the value of level_vy2")

		if c_m._range is not None:
		    c_m.rotate_val_in_range(c_m._c[c_m._vy0][c_m._vy1][c_m._vy2])
		if c_m._cand is not None:
		    c_m.rotate_val_from_cand(c_m._c[c_m._vy0][c_m._vy1][c_m._vy2])
		c_m._c[c_m._vy0][c_m._vy1][c_m._vy2]['mod'] = 1
	    else: return

	ld.clear_display()
	c_m.refresh_display()

    #
    #  find updated config data and treat them
    #
    @staticmethod
    def check_modified_items():

	logger = logging.getLogger(__name__)
	logger.debug("check_modified_items")

	print var_dump(c_m._c)
	for lv0 in c_m._c:
	    mod_val =  c_m._c[lv0].pop('mod', None)
	    if mod_val != None:
		if lv0 == 'reset_settings':
		    logger.debug("cmi: reset_settings")
		    c_m.init()
		    return;
	    if 'value' in c_m._c[lv0]: continue;

	    for lv1 in c_m._c[lv0]:
		mod_val = c_m._c[lv0][lv1].pop('mod', None)
		if 'value' in c_m._c[lv0][lv1]: continue;

		logger.debug("cmi: check " + lv1)
		for lv2 in c_m._c[lv0][lv1]:
		    mod_val = c_m._c[lv0][lv1][lv2].pop('mod', None)
		    if mod_val != None:
			if lv1.startswith('alarm'):
			    logger.debug("cmi: reset " + lv1)
			    al_a.setAlarm(lv1)

    @staticmethod
    def redraw_display():

	ld.set_double_height(0)
	c_m.refresh_display()

    @staticmethod
    def refresh_display():

	logger = logging.getLogger(__name__)

	logger.debug("refresh_display")
	logger.debug("1: {} - {} - {} sublevel={}".format(c_m._vy0,c_m._vy1,c_m._vy2,c_m._sublevel))

	if c_m._vy0 is None: c_m.rotate_vy0()

	if c_m._vy2 is not None:
	    logger.debug("hierical-2")
	    n_objs = c_m._c[c_m._vy0][c_m._vy1]
	    n_vx = 0
	    for t_key, t_obj in n_objs.items():
		ld.write_char(t_key, 0, n_vx)
		ld.write_char(str(t_obj['value']), 1, n_vx)
		n_objs[t_key]['vx'] = n_vx
		n_vx += len(t_key) + 1

	    ld.set_location(1, int(n_objs[c_m._vy2]['vx']))
	    ld.cursor_sw(1)

        elif c_m._vy1 is not None:
	    if c_m._sublevel:
		logger.debug("hierical-1")
		ld.cursor_sw(0)
		ld.write_char(c_m._vy1 + ' >', 0, 0)
		n_vx = 0
		for t_key in c_m._c[c_m._vy0][c_m._vy1].keys():
		   ld.write_char(t_key, 1, n_vx)
		   n_vx += len(t_key) + 1

	    else:
		logger.debug("val select(multi)")
		ld.write_char(c_m._vy1, 0, 0)
		ld.write_char(str(c_m._c[c_m._vy0][c_m._vy1]['value']), 1, 0)

		ld.set_location(1, 0)
		ld.cursor_sw(1)

	else:
	    if c_m._sublevel:
		logger.debug("item select(multi)")
		ld.cursor_sw(0)
		ld.write_char(c_m._vy0 + ' >', 0, 0)
		n_vx = 0
		for t_key in c_m._c[c_m._vy0].keys():
		   ld.write_char(t_key, 1, n_vx)
		   n_vx += len(t_key) + 1

	    else:
		logger.debug("value select(single)")
		ld.write_char(c_m._vy0, 0, 0)
		ld.write_char(str(c_m._c[c_m._vy0]['value']), 1, 0)

		ld.set_location(1, 0)
		ld.cursor_sw(1)

######################################################################
#  Alarm application

class al_a:

    _mode = 'none'
    _cand = ('none', 'alarm', 'snooze')
    _queue = {}
    _ordered_queue = None
    _recent_val = None		# 直近のアラーム発動時刻

    @staticmethod
    def init():
	logger = logging.getLogger(__name__)
	al_a.setAlarm(None)


    @staticmethod
    def key_event(key_status):
	logger = logging.getLogger(__name__)

	if al_a._mode == 'alarm':
	    # 'alarm'中にボタンを押されたら'snooze'に移行
	    al_a._mode = 'snooze'
	    al_a._submode = key_status
	    al_a._keycount = 1
	    al_a.stop_process()
	    al_a.setAlarm()     # 次の鳴動時間まで待機

	elif al_a._mode == 'snooze':
	    if al_a._submode == key_status:
		al_a._keycount += 1
		# 'snooze'中に同じボタンを続けて3回押すと'snooze'解除とする
		if al_a._keycount == 3:
		    al_a._submode = 0
		    al_a._keycount = 0
		    al_a.setAlarm(None)         # 今回の動作は終了させて次回を再スケジュール
	    else:
		# 途中で違うボタンが押されたらカウンターを１に戻してやり直し
		al_a._submode = key_status
		al_a._keycount = 1

	al_a.refresh_display()
        
    @staticmethod
    def redraw_display():

	ld.set_double_height(0)
	al_a.refresh_display()


    @staticmethod
    def refresh_display():

	sht = { 'alarm1':'A1', 'alarm2':'A2', 'alarm3':'A3' }	# 省略名

	logger = logging.getLogger(__name__)
	iter_q = iter(al_a._ordered_queue)
	try:
	    next_key = next(iter_q)
	    next_val = al_a._ordered_queue[next_key]
	    dt = datetime.fromtimestamp(next_val)
	    next_time = dt.strftime(" %m/%d %H:%M")
	    ld.write_char(sht[next_key] + next_time , 0, 0)
	except StopIteration:
	    ld.write_char(" - - -", 0, 0)
	    return

	try:
	    next_key = next(iter_q)
	    next_val = al_a._ordered_queue[next_key]
	    dt = datetime.fromtimestamp(next_val)
	    next_time = dt.strftime(" %m/%d %H:%M")
	    ld.write_char(sht[next_key] + next_time , 1, 0)
	except StopIteration:
	    ld.write_char(" - - -", 1, 0)


    @staticmethod
    def polling():
	logger = logging.getLogger(__name__)

	if al_a._mode == 'alarm': return

	if al_a._rectnt_val is not None:
	    if time.time() >= al_a._recent_val:
		al_a._mode = 'alarm'
		exec_player()

    #
    # reschedule the alarm
    #
    @staticmethod
    def setAlarm(alarm_name):

	logger = logging.getLogger(__name__)
	logger.debug("setAlarm:"+str(alarm_name))
	if alarm_name == None or alarm_name == 'alarm1':
	    if c_m._c['alarm']['alarm1']['sw ']['value'] == 'ON':
		ts = al_a.calc_next_alarm(c_m._c['alarm']['alarm1'])
		al_a._queue['alarm1'] = ts
		logger.debug("alarm1" +  str(ts))
	    else:
		ts = al_a._queue.pop('alarm1', None)
		logger.debug("remove alarm1:"+ str(ts))

	if alarm_name == None or alarm_name == 'alarm2':
	    if c_m._c['alarm']['alarm2']['sw ']['value'] == 'ON':
		ts = al_a.calc_next_alarm(c_m._c['alarm']['alarm2'])
		al_a._queue['alarm2'] = ts
		logger.debug("alarm1" +  str(ts))
	    else:
		ts = al_a._queue.pop('alarm2', None)
		logger.debug("remove alarm2:"+ str(ts))

	if alarm_name == None or alarm_name == 'alarm3':
	    if c_m._c['alarm']['alarm3']['sw ']['value'] == 'ON':
		ts = al_a.calc_next_alarm(c_m._c['alarm']['alarm3'])
		al_a._queue['alarm3'] = ts
		logger.debug("alarm1" +  str(ts))
	    else:
		ts = al_a._queue.pop('alarm3', None)
		logger.debug("remove alarm3:"+ str(ts))

	al_a._ordered_queue = OrderedDict(sorted(al_a._queue.items(), key=lambda x:x[1]))
	iter_q = iter(al_a._ordered_queue)
	try:
	    al_a._recent_val = al_a._ordered_queue[next(iter_q)]
	except StopIteration:
	    al_a._recent_val = None


    @staticmethod
    def calc_next_alarm(alarm_info):

	logger = logging.getLogger(__name__)
	wk = alarm_info['wek']['candidate'].index(alarm_info['wek']['value'])
	h  = alarm_info['h ']['value']
	m  = alarm_info['m ']['value']
	logger.debug(str(wk)+":"+str(h)+":"+str(m))
	dt_now = datetime.now()
	dt_al_1 = dt_now.replace(hour=h,minute=m,second=0,microsecond=0)

	if wk < 7:      # set specified day
	    wk_diff = wk - dt_now.weekday()	# 今日とターゲット曜日の差分から次回を計算
	    if wk_diff < 0 : wk_diff += 7
	    dt_al_1 += timedelta(days=wk_diff)
	    logger.debug("wd:wk_diff="+str(wk_diff))
	    if dt_al_1 < dt_now: dt_al_1 += timedelta(days=7)

	elif wk == 7:   # set week day
	    wk_diffs1 = (0, 0, 0, 0, 0, 2, 1)	# 今日が何曜日かで次回までの日数が変わる
	    wk_diffs2 = (1, 1, 1, 1, 3, 0, 0)	# 次を同じ日に鳴らす場合はこのリストは使わず
	    wk_diff = wk_diffs1[dt_now.weekday()]
	    logger.debug("wd:wk_diff="+str(wk_diff))
	    dt_al_1 += timedelta(days=wk_diff)
	    if dt_al_1 < dt_now: dt_al_1 += timedelta(days=wk_diff2[dt_now.weekday()])

	elif wk == 8:   # set holyday
	    wk_diffs1 = (5, 4, 3, 2, 1, 0, 6)	# 今日が何曜日かで次回までの日数が変わる
	    wk_diffs2 = (0, 0, 0, 0, 0, 1, 0)	# 次を同じ日に鳴らす場合はこのリストは使わず
	    wk_diff = wk_diffs1[dt_now.weekday()]
	    logger.debug("wd:wk_diff="+str(wk_diff))
	    dt_al_1 += timedelta(days=wk_diff)
	    if dt_al_1 < dt_now: dt_al_1 += timedelta(days=wk_diffs2[dt_now.weekday()])

	return time.mktime(dt_al_1.timetuple())

######################################################################
#  MAIN

logging.basicConfig(format='%(asctime)s %(funcName)s %(message)s', filename='/tmp/p3.log',level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())

c_m.init()
al_a.init()

__i2c = smbus.SMBus(1)
ld.init(__i2c)

d_m.init(__i2c)
m_time = (time.time() // 60)

time.sleep(5)
d_m.resume_hsd()

try:
    while 1:
	time.sleep(0.25)
	d_m.polling()

	if (m_time != (time.time()) // 60):
	    m_time = (time.time()) // 60

	    logger.debug("Do refresh Display")
	    d_m.refresh_display()
	    d_m.resume_hsd()

except KeyboardInterrupt:

    GPIO.cleanup()


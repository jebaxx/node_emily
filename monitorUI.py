#!/usr/bin/python
#
import sys
import logging
import time
import RPi.GPIO as GPIO
import smbus
from collections import OrderedDict
from datetime import datetime
from shutil import copyfile

__i2c = None

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
    _states = [ 'config', 'clock', 'sensor' ]

    I2CADDR_BTN  = 0x3f  # button shim I2C Address
    _key_state   = 0
    _current_sw  = 0

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
    _c_form_no = 0

    _sens_form = [	'{temp:05.2f}C   {hum:04.1f}%' ,
			' {temp:05.2f}C   {hum:04.1f}%' ,
			'  {temp:05.2f}C  {hum:04.1f}%' ]

    _s_form_no = 0
    _sc_form_no = 0

    @staticmethod
    def init(__i2c) :
	logger = logging.getLogger(__name__)
	d_m._i2c = __i2c
	d_m._state = c_m.get('initial_dm_state')
	GPIO.setmode( GPIO.BCM )
	GPIO.setup( 27, GPIO.IN )
	GPIO.add_event_detect( 27, GPIO.FALLING, callback = d_m.button_callback )
	ld.init(__i2c)
	d_m.redraw_display()

    #
    #  set configuration
    #
    @staticmethod
    def set_initial_state(new_state) :
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

    #
    #  Change d_m_status
    #
    @staticmethod
    def change_state():

	i = d_m._states.index(d_m._state) + 1
	if i == len(d_m._states): i = 0
	d_m._state = d_m._states[i]

	ld.clear_display()

	if d_m._state == 'config':
	    c_m.redraw_display()
	else:
	    d_m.redraw_display()

    #
    #  key event handler
    #
    @staticmethod
    def key_event(key_state) :

	logger = logging.getLogger(__name__)
	if d_m._state == 'clock':
	    if key_state & 0b001010 :
		d_m._c_form_no += 1
		if d_m._c_form_no == len(d_m._clock_form): d_m._c_form_no = 0
	    elif key_state & 0b010100 :
		d_m._c_form_no -= 1
		if d_m._c_form_no == -1: d_m._c_form_no = len(d_m._clock_form) - 1

	    ld.clear_display()
	    d_m.redraw_display()

	elif d_m._state == 'sensor':
	    if key_state & 0b000010 :
		d_m._sc_form_no += 1
		if d_m._sc_form_no == len(d_m._clock_form)+1 : d_m._sc_form_no = 0
	    elif key_state & 0b000100 :
		d_m._sc_form_no -= 1
		if d_m._sc_form_no == -1 : d_m._sc_form_no = len(d_m._clock_form)
	    elif key_state & 0b001000 :
		d_m._s_form_no += 1
		if d_m._s_form_no == len(d_m._sens_form) : d_m._s_form_no = 0
	    elif key_state & 0b010000 :
		d_m._s_form_no -= 1
		if d_m._s_form_no == -1 : d_m._s_form_no = len(d_m._sens_form) - 1

	    d_m.redraw_display()

    #
    #  redraw display
    #
    @staticmethod
    def redraw_display():

	ld.clear_display()
	ld.cursor_sw(0)
	if d_m._state == 'clock' or d_m._sc_form_no == 0 : ld.set_double_height(1)
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

	if d_m._state == 'clock':
	    ld.write_char(datetime.now().strftime(d_m._clock_form[d_m._c_form_no]), 0, 0)
	elif d_m._state == 'sensor':
	    temp, temp_c, hum = d_m.read_sens_data()
	    if d_m._sc_form_no != 0 :
		ld.write_char(datetime.now().strftime(d_m._clock_form[d_m._sc_form_no-1]), 0, 0)
		ld.write_char(d_m._sens_form[d_m._s_form_no].format(temp=temp, hum=hum), 1, 0)
	    else :
		ld.write_char(d_m._sens_form[d_m._s_form_no].format(temp=temp, hum=hum), 0, 0)
	elif d_m._state == 'config':
	    c_m.refresh_display()
	else:
	    ld.write_char('unknown', 0, 0)



######################################################################
#  Sub process (cooperate with monitorBase)
#
#	manage LED display and button devices
#====================================================================#


######################################################################
#  config manager class

class c_m:
        
    _c = OrderedDict()
    _c['initial_dm_state'] = { 'value':'clock', 'candidate':('clock', 'sensor', 'alarm', 'config') }
    _c['hsd_mode'] = { 'value':0 , 'range':( 0, 1 ) }
    _c['clock_style'] = { 'value':1 , 'range':( 0, 10 ) }

    _c['sens_style'] = OrderedDict()
    _c['sens_style']['sens'] = { 'value':1, 'range':( 0, 3 ) } 
    _c['sens_style']['clock'] = { 'value':1, 'range':( 0, 10) } 

    _c['alarm'] =  OrderedDict()
    _c['alarm']['alarm1'] = OrderedDict()
    _c['alarm']['alarm1']['sw '] = { 'value':'OFF', 'candidate':( 'ON ', 'OFF' ) }
    _c['alarm']['alarm1']['wek'] = { 'value':'wek', 'candidate':( 'mon', 'tue', 'wed', 'thr', 'fri', 'sat', 'sun', 'wek', 'hol') }
    _c['alarm']['alarm1']['h '] = { 'value':6, 'range':( 0, 23 ) }
    _c['alarm']['alarm1']['m '] = { 'value':45, 'range':( 0, 59 ) }

    _c['alarm']['alarm2'] = OrderedDict()
    _c['alarm']['alarm2']['sw '] = { 'value':'OFF', 'candidate':( 'ON', 'OFF' ) }
    _c['alarm']['alarm2']['wek'] = { 'value':'wek', 'candidate':( 'mon', 'tue', 'wed', 'thr', 'fri', 'sat', 'sun', 'wek', 'hol') }
    _c['alarm']['alarm2']['h '] = { 'value':7, 'range':( 0, 23 ) }
    _c['alarm']['alarm2']['m '] = { 'value':30, 'range':( 0, 59 ) }

    _c['alarm']['alarm3'] = OrderedDict()
    _c['alarm']['alarm3']['sw '] = { 'value':'OFF', 'candidate':( 'ON', 'OFF' ) }
    _c['alarm']['alarm3']['wek'] = { 'value':'wek', 'candidate':( 'mon', 'tue', 'wed', 'thr', 'fri', 'sat', 'sun', 'wek', 'hol') }
    _c['alarm']['alarm3']['h '] = { 'value':5, 'range':( 0, 23 ) }
    _c['alarm']['alarm3']['m '] = { 'value':50, 'range':( 0, 59 ) }

    _vy0 = 0
    _vy1 = None
    _vy2 = None
    _sublevel = False
    _level = None

    _cand = None
    _range = None

    @staticmethod
    def get(conf_name):
	return c_m._c[conf_name]['value']

    @staticmethod
    def key_event(key_state):
	logger = logging.getLogger(__name__)

	logger.debug("key_event:" + str(key_state) + " ******")
	logger.debug("0: {} - {} - {} level={} sublevel={}".format(c_m._vy0,c_m._vy1,c_m._vy2,c_m._level,c_m._sublevel))

	if key_state & 0b000010 :
	    logger.debug("level 0 next")
	    c_m._vy0 += 1
	    c_m._vy1 = None
	    c_m._vy2 = None

	    ld.clear_display()
	    if not c_m.refresh_display() :
		c_m._vy0 = 0
		c_m.refresh_display()

	elif key_state & 0b000100 :
	    if c_m._level >= 1 or (c_m._level == 0 and c_m._sublevel):
		logger.debug("level 1 next")
		if c_m._vy1 == None : c_m._vy1 = 0
		else:		  c_m._vy1 += 1
		c_m._vy2 = None

	    elif c_m._level == 0 and not c_m._sublevel:
		logger.debug("level 1 value select")
		prim_key = c_m._c.keys()[c_m._vy0]

		if c_m._range is not None:
		    c_m._c[prim_key]['value'] += 1
		    if c_m._c[prim_key]['value'] > c_m._range[1]:
			c_m._c[prim_key]['value'] = c_m._range[0]

		if c_m._cand is not None:
		    idx = c_m._cand.index(c_m._c[prim_key]['value']) + 1
		    if idx == len(c_m._cand): idx = 0
		    c_m._c[prim_key]['value'] = c_m._cand[idx]

	    ld.clear_display()
	    if not c_m.refresh_display() :
		c_m._vy1 = 0
		logger.debug("key_event: retry")
		c_m.refresh_display()

	elif key_state & 0b001000 :
	    if c_m._level == 2 or (c_m._level == 1 and c_m._sublevel):
		logger.debug("level2 next")
		if c_m._vy2 == None : c_m._vy2 = 0
		else:		  c_m._vy2 += 1

	    elif c_m._level == 1 and not c_m._sublevel:
		logger.debug("level2 value select")
		prim_key = c_m._c.keys()[c_m._vy0]
		prim_obj = c_m._c[prim_key]
		second_key = prim_obj.keys()[c_m._vy1]
		second_obj = prim_obj[second_key]

		if c_m._range is not None:
		    second_obj['value'] += 1
		    if second_obj['value'] > c_m._range[1]:
			second_obj['value'] = c_m._range[0]

		if c_m._cand is not None:
		    idx = c_m._cand.index(second_obj['value']) + 1
		    if idx == len(c_m._cand): idx = 0
		    second_obj['value'] = c_m._cand[idx]

	    ld.clear_display()
	    if not c_m.refresh_display() :
		c_m._vy2 = 0
		logger.debug("key_event: retry")
		c_m.refresh_display()

	elif key_state & 0b010000:
	    if c_m._level != 2 or c_m._sublevel: return
	    logger.debug("level3 value select")

	    prim_key = c_m._c.keys()[c_m._vy0]
	    prim_obj = c_m._c[prim_key]
	    second_key = prim_obj.keys()[c_m._vy1]
	    second_obj = prim_obj[second_key]
	    third_key = second_obj.keys()[c_m._vy2]
	    third_obj = second_obj[third_key]

	    if c_m._range is not None:
		logger.debug("  range= ( {} - {} )".format(c_m._range[0], c_m._range[1]))
		third_obj['value'] += 1
		if third_obj['value'] > c_m._range[1]:
		    third_obj['value'] = c_m._range[0]
		logger.debug("next value = " + str(third_obj['value']) + "(r)")

	    if c_m._cand is not None:
		logger.debug("  cand = ( {} / {} / ...)".format(c_m._cand[0], c_m._cand[1]))
		idx = c_m._cand.index(third_obj['value']) + 1
		if idx == len(c_m._cand): idx = 0
		third_obj['value'] = c_m._cand[idx]
		logger.debug("next value = " + str(third_obj['value']) + "(c)")

	    ld.clear_display()
	    c_m.refresh_display()

    @staticmethod
    def redraw_display():

	ld.set_double_height(0)
	c_m.refresh_display()

    @staticmethod
    def refresh_display():
	logger = logging.getLogger(__name__)

	logger.debug("refresh_display")
	logger.debug("1: {} - {} - {} level={} sublevel={}".format(c_m._vy0,c_m._vy1,c_m._vy2,c_m._level,c_m._sublevel))
	if len(c_m._c.keys()) <= c_m._vy0: return False
	prim_key = c_m._c.keys()[c_m._vy0]
	prim_obj = c_m._c[prim_key]
	n_title  = None
	n_value  = None
	n_subtitles = None
	n_titles = None
	n_objs   = None
	c_m._cand = None
	c_m._range = None

	if 'value' in prim_obj:
	    #single value
	    #
	    n_title = prim_key
	    n_value = prim_obj['value']
	    c_m._cand  = prim_obj.get('candidate')
	    c_m._range = prim_obj.get('range')
	    c_m._level = 0
	    c_m._sublevel = False
	else:
	    #multi value
	    #
	    if (c_m._vy1 == None): 
		n_title = prim_key
		n_subtitles = prim_obj.keys()
		c_m._level = 0
		c_m._sublevel = True
	    else:
		if len(prim_obj.keys()) <= c_m._vy1: return False
		second_key = prim_obj.keys()[c_m._vy1]
		second_obj = prim_obj[second_key]

		if 'value' in second_obj:
		    n_title = second_key
		    n_value = second_obj['value']
		    c_m._cand  = second_obj.get('candidate')
		    c_m._range = second_obj.get('range')
		    c_m._level = 1
		    c_m._sublevel = False
		else:
		    #hierarchal value
		    #
		    if (c_m._vy2 == None):
			logger.debug("hierical-1")
			n_title = second_key
			n_subtitles = []
			for third_obj in second_obj.values():
			    n_subtitles.append(str(third_obj['value']))
			c_m._level = 1
			c_m._sublevel = True
		    else:
			logger.debug("hierical-2")
			if len(second_obj.keys()) <= c_m._vy2: return False
			n_titles = []
			n_objs = OrderedDict()
			n_vx = 0
			for t_key, t_obj in second_obj.items():
			    n_titles.append(t_key)
			    n_objs[t_key] = t_obj
			    n_objs[t_key]['vx'] = n_vx
			    n_vx += len(t_key) + 1
			t_key = n_titles[c_m._vy2]
			c_m._range = n_objs[t_key].get('range')
			c_m._cand  = n_objs[t_key].get('candidate')
			c_m._level = 2
			c_m._sublevel = False

	logger.debug("2: {} - {} - {} level={} sublevel={}".format(c_m._vy0,c_m._vy1,c_m._vy2,c_m._level,c_m._sublevel))

	ld.cursor_sw(0)
	if n_title is not None:
	    ld.write_char(n_title, 0, 0)
	if n_titles is not None:
	    for title in n_titles:
		n_vx = n_objs[title]['vx']
		ld.write_char(title, 0, n_vx)
		ld.write_char(str(n_objs[title]['value']), 1, n_vx)
		ld.set_location(1, 0)
	if n_value is not None: 
	    ld.write_char(str(n_value), 1, 0)
	    ld.set_location(1, 0)
	    ld.cursor_sw(1)
	if n_subtitles is not None:
	    vx = 0
	    for subtitle in n_subtitles:
		ld.write_char(str(subtitle), 1, vx)
		vx += len(subtitle) + 1
	if n_objs is not None:
	    t_key = n_titles[c_m._vy2]
	    ld.set_location(1, int(n_objs[t_key]['vx']))
	    ld.cursor_sw(1)

	return True

######################################################################
#  MAIN

logging.basicConfig(format='%(asctime)s %(funcName)s %(message)s', filename='/tmp/p3.log',level=logging.INFO)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())


__i2c = smbus.SMBus(1)
ld.init(__i2c)

d_m.init(__i2c)
m_time = (time.time() // 60)

time.sleep(5)
try:
    with open('/tmp/pipe', 'w') as f:
	f.write(str(c_m.get('hsd_mode')))
except EnvironmentError:
    logger.error("pipe cannot open")
    sys.exit()

try:
    while 1:
	time.sleep(0.25)
	d_m.polling()

	if (m_time != (time.time()) // 60):
	    m_time = (time.time()) // 60

	    logger.debug("Do refresh Display")
	    d_m.refresh_display()
	    try:
		with open('/tmp/pipe', 'w') as f:
		    f.write(str(c_m.get('hsd_mode')))
	    except EnvironmentError:
		logger.error("pipe cannot open")
		sys.exit()

except KeyboardInterrupt:

    GPIO.cleanup()



#!/usr/bin/python
#
import sys
import logging
import time
import RPi.GPIO as GPIO
import smbus
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
	if sw == 1:
	    ld.so_cmd(0x0c)
	else:
	    ld.so_cmd(0x08)

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
	logger.debug("key_detect:" + str(key_state))

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
#  config manager class

class c_m:
        
    _conf = {}
    _conf['initial_dm_state'] = 'clock'
    _conf['hsd_mode'] = 1
    
    @staticmethod
    def get(conf_name):

	return c_m._conf[conf_name]

    @staticmethod
    def redraw_display():

	ld.set_double_height(1)
	c_m.refresh_display()

    @staticmethod
    def refresh_display():

	ld.write_char('config', 0, 0)

    @staticmethod
    def key_event(key_state):

	pass

######################################################################
#  MAIN

logging.basicConfig(format='%(asctime)s %(funcName)s %(message)s', filename='/tmp/p2.log',level=logging.INFO)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())


__i2c = smbus.SMBus(1)
ld.init(__i2c)

d_m.init(__i2c)
m_time = (time.time() // 60)

hsd_mode = c_m.get('hsd_mode')
time.sleep(5)
try:
    with open('/tmp/pipe', 'w') as f:
	f.write(str(hsd_mode))
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
		    f.write(str(hsd_mode))
	    except EnvironmentError:
		logger.error("pipe cannot open")
		sys.exit()

except KeyboardInterrupt:

    GPIO.cleanup()


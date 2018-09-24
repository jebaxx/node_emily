#!/usr/bin/python
#
import os
import errno
import logging
import time
import RPi.GPIO as GPIO
import threading
import smbus
from datetime import datetime
import requests
import math

__i2c = None

######################################################################
#  MAIN process
#
#	Read senser data periodically and POST to a GAE server
#	and the local file (for local UI)
#====================================================================#

#====================================================================#
#  3 color led controller class
#====================================================================#

class c3_m:

    _i2c = None
    _t1  = 0
    _t2r = 0
    _t2g = 0
    _t2b = 0
    _dt  = 1/4.0

    #- - - - - - - - - - - - - - - - - -
    # LED controller constant

    i2cAddr_BTN = 0x3f

    REG_INPUT    = 0x00
    REG_OUTPUT   = 0x01
    REG_POLARITY = 0x02
    REG_CONFIG   = 0x03

    LED_DATA = 7
    LED_CLOCK = 6

    LED_GAMMA = [
	  0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,
	  0,   0,   0,   0,   0,   0,   1,   1,   1,   1,   1,   1,   1,   2,   2,   2,
	  2,   2,   2,   3,   3,   3,   3,   3,   4,   4,   4,   4,   5,   5,   5,   5,
	  6,   6,   6,   7,   7,   7,   8,   8,   8,   9,   9,   9,  10,  10,  11,  11,
	 11,  12,  12,  13,  13,  13,  14,  14,  15,  15,  16,  16,  17,  17,  18,  18,
	 19,  19,  20,  21,  21,  22,  22 , 23,  23,  24,  25,  25,  26,  27,  27,  28,
	 29,  29,  30,  31,  31,  32,  33,  34,  34,  35,  36,  37,  37,  38,  39,  40,
	 40,  41,  42,  43,  44,  45,  46,  46,  47,  48,  49,  50,  51,  52,  53,  54,
	 55,  56,  57,  58,  59,  60,  61,  62,  63,  64,  65,  66,  67,  68,  69,  70,
	 71,  72,  73,  74,  76,  77,  78,  79,  80,  81,  83,  84,  85,  86,  88,  89,
	 90,  91,  93,  94,  95,  96,  98,  99, 100, 102, 103, 104, 106, 107, 109, 110,
	111, 113, 114, 116, 117, 119, 120, 121, 123, 124, 126, 128, 129, 131, 132, 134,
	135, 137, 138, 140, 142, 143, 145, 146, 148, 150, 151, 153, 155, 157, 158, 160,
	162, 163, 165, 167, 169, 170, 172, 174, 176, 178, 179, 181, 183, 185, 187, 189,
	191, 193, 194, 196, 198, 200, 202, 204, 206, 208, 210, 212, 214, 216, 218, 220,
	222, 224, 227, 229, 231, 233, 235, 237, 239, 241, 244, 246, 248, 250, 252, 255]

    _brightness = 0.8

    @staticmethod
    def init(__i2c):
	c3_m._i2c = __i2c

	c3_m._i2c.write_byte_data(c3_m.i2cAddr_BTN, c3_m.REG_CONFIG, 0b00011111)
	c3_m._i2c.write_byte_data(c3_m.i2cAddr_BTN, c3_m.REG_POLARITY, 0b00000000)
	c3_m._i2c.write_byte_data(c3_m.i2cAddr_BTN, c3_m.REG_OUTPUT, 0b00000000)

	c3_m.set_pixel(0, 100, 200)

    @staticmethod
    def _write_byte(byte):
	cmd = []
	for x in range(8):
	    if (byte & 0b10000000) : _cmd = (1 << c3_m.LED_DATA)
	    else:			 _cmd = 0
	    cmd.append(_cmd)
	    _cmd |= (1 << c3_m.LED_CLOCK)
	    cmd.append(_cmd)
	    byte <<= 1

	c3_m._i2c.write_i2c_block_data(c3_m.i2cAddr_BTN, c3_m.REG_OUTPUT, cmd)

    @staticmethod
    def set_pixel(r, g, b):
	r, g, b = [int(x * c3_m._brightness) for x in (r, g, b)]

	c3_m._write_byte(0)
	c3_m._write_byte(0)
	c3_m._write_byte(0b11101111)
	c3_m._write_byte(c3_m.LED_GAMMA[b & 0xff])
	c3_m._write_byte(c3_m.LED_GAMMA[g & 0xff])
	c3_m._write_byte(c3_m.LED_GAMMA[r & 0xff])
	c3_m._write_byte(0)
	c3_m._write_byte(0)

    @staticmethod
    def polling():

	c3_m._t1 += c3_m._dt
	mtr = abs((c3_m._t1 % 80) - 40) + 10.0
	mtg = abs((c3_m._t1 % 82) - 41) + 10.1
	mtb = abs((c3_m._t1 % 84) - 42) + 9.9
	
	c3_m._t2r += c3_m._dt / mtr
	c3_m._t2g += c3_m._dt / mtg
	c3_m._t2b += c3_m._dt / mtb

	Lr = math.sin(c3_m._t2r * math.pi) * 180 + 60
	if Lr < 0 : Lr = 0
	Lg = math.sin(c3_m._t2g * math.pi) * 180 + 60
	if Lg < 0 : Lg = 0
	Lb = math.sin(c3_m._t2b * math.pi) * 180 + 60
	if Lb < 0 : Lb = 0
	c3_m.set_pixel(Lr, Lg, Lb)

#====================================================================#
#  LED display ON / OFF  controller class
#====================================================================#

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
    def init_1602() :

	ld.DH  = 0
	ld.DHD = 1
	ld.clear_display()
	ld.ms_delay(20)

    # # PUBLIC METHODS # #

    @staticmethod
    def init(i2c):
	ld._i2c = i2c
	ld.init_1602()

    @staticmethod
    def clear_display() :
	ld.so_cmd(0x01)

    @staticmethod
    def display_sw(sw):
	if sw == 1:
	    ld.so_cmd(0x0c)
	else:
	    ld.so_cmd(0x08)

#====================================================================#
#  heat source detector class
#====================================================================#

class hsd:

    _mode = 0			# 0:mode off , 1: hsd mode
    _is_someone = 0
    _dtect_count = 0		# detection signal count in a minute
    _t_detect = None		# the time of sensor detect heat source(=null when _is_someone == false)
    _t_confirming = None	# when the sensor detect twice within 3.0 second, it's regard as "detection". 
				#  This store the first detection time.
    _detect_count = 0

    @staticmethod
    def init():

	GPIO.setmode( GPIO.BCM )
	GPIO.setup( 10, GPIO.IN )
	GPIO.add_event_detect( 10, GPIO.RISING, callback = hsd.hsd_callback )

	hsd._t_confirming = time.time()

	if hsd._mode == 0 :
	    hsd._is_someone= 1
	else :
	    hsd._is_someone= 0

	return

    #
    #  set configuration
    #
    @staticmethod
    def set_mode(new_mode) :
	logger = logging.getLogger(__name__)

	if hsd._mode == new_mode:
	    return

	hsd._mode = new_mode
	if hsd._mode== 0 :
	    logger.info("set_mode:_is_someone = 1")
	    hsd._is_someone = 1
	else :
	    logger.info("set_mode:_is_someone = 0")
	    hsd._is_someone = 0

    #
    # hsd callback
    #
    #   update _t_detect by current time
    #
    @staticmethod
    def hsd_callback(portNo):

	logger = logging.getLogger(__name__)
	hsd._t_detect = time.time()
	logger.debug("hsd triggered")
	hsd._detect_count += 1

	return

    @staticmethod
    def get_detect_count():

	return_val = hsd._detect_count
	hsd._detect_count = 0
	return return_val
        
    #
    #   expected to be called periodically
    #
    #    decide _is_someone or not
    #
    @staticmethod
    def polling():

	logger = logging.getLogger(__name__)
	if hsd._mode == 0 or hsd._t_detect == None :
	    # there is nothing to do in this condition
	    return

	if hsd._is_someone :
	    # aleady acquired
	    if time.time() - hsd._t_detect > 10 :
		hsd._is_someone = 0
		hsd._t_detect = None
		logger.debug("hsd: leaved")

	elif (hsd._t_confirming == None) or (hsd._t_detect - hsd._t_confirming > 3.0) :
	    # first event
	    hsd._t_confirming = hsd._t_detect
	    hsd._t_detect = None
	    logger.debug("hsd: confirming...")

	else :
	    # subsequent event(now acquireing)
	    hsd._t_confirming = None
	    hsd._is_someone = 1
	    logger.debug("hsd: detect")

	return

#====================================================================#
#  message acceptor (from child process)
#====================================================================#

class m_a:

    _hsd_mode = 2	# 0/1 : the same as hsd._mode, 
			# 2   : hsd mechanism is closed because of stagnation of a message from UI module
    _t_received = 0
    _fifo = '/tmp/pipe'
    _led_current = 0

    @staticmethod
    def init():
	logger = logging.getLogger(__name__)

	m_a._t_received = time.time()
	try:
	    os.mkfifo(m_a._fifo)
	except EnvironmentError as ee:
	    logger.info("fifo cannot create:" + str(ee.errno))
	    if ee.errno != errno.EEXIST:
		logger.error("fifo cnnot create" + ee.args)
		raise

	th = threading.Thread(target = m_a.fifo_listner)
	th.setDaemon(True)
	th.start()

    @staticmethod
    def fifo_listner():
	logger = logging.getLogger(__name__)

	while True:
	    logger.debug("waiting fifo...");
	    with open (m_a._fifo) as f:
		data = f.read()
		if len(data) == 0 : break
		m_a._hsd_mode = int(data)
		m_a._t_received = time.time()
		logger.debug("data received from fifo " + str(m_a._hsd_mode))
		hsd.set_mode(m_a._hsd_mode)

    @staticmethod
    def polling():
	logger = logging.getLogger(__name__)

	if m_a._hsd_mode == 2:
            # hsd is closed. 
            # This could be changed by a reconnected UI module.
	    return

	if time.time() - m_a._t_received > 125:
            # UI module is not active
	    if m_a._hsd_mode != 2:
		logger.warning("fifo timeout... hsd is closed")
		m_a._hsd_mode = 2
		m_a._led_current = 0
		logger.debug("led OFF");
		ld.display_sw(0)
	else:
	    if m_a._led_current != hsd._is_someone :
		# UI module change the hsd_mode
		m_a._led_current = hsd._is_someone
		if m_a._led_current == 1 :
		    logger.debug("led ON");
		    ld.display_sw(1)
		else:
		    logger.debug("led OFF");
		    ld.display_sw(0)

#====================================================================#
#  update sens data 
#====================================================================#

#
#   Get CPU temperature
#
def get_cpu_thermal():
    f = open('/sys/class/thermal/thermal_zone0/temp','r')
    temp_c = long(f.read()) / 1000.0
    f.close()

    return temp_c


#
#   SHT-31 sensor read
#
i2cAddr_SHT31 = 0x45

def measure_T_H():

    global __i2c

    logger = logging.getLogger(__name__)
    logger.debug("read from sensor device...")
    __i2c.write_i2c_block_data(i2cAddr_SHT31, 0x2c, [0x06])
    time.sleep(0.02)
    data = __i2c.read_i2c_block_data(i2cAddr_SHT31, 0, 6)

    temp_s   = ( 175 * (data[0] * 256 + data[1]) / 65535.0) - 45
    humidity =   100 * (data[3] * 256 + data[4]) / 65535.0

    logger.debug("{:05.2f}C {:04.1f}%".format(temp_s, humidity))

    return temp_s, humidity

#
#   write sensed data to the data file and the server
#
def sens_and_record():

    (temp_s, humidity) = measure_T_H()
    temp_c = get_cpu_thermal()

    with open('/tmp/sens_data.txt', 'w') as f:
	f.write(str(temp_s)+','+ str(temp_c) + ',' + str(humidity))

    return temp_s, temp_c, humidity

#
#   POST to GAE
#
def postToGAE(temp_s, temp_c, humidity, sensCount):

    logger = logging.getLogger(__name__)

    postUrl = "https://jebaxxmonitor.appspot.com/postData"
    params = { 
	"sensData[%s]" % "timestamp" : datetime.now().isoformat(),
	"sensData[%s]" % "T-SHT-31"  : temp_s ,
	"sensData[%s]" % "H-SHT-31"  : humidity ,
	"sensData[%s]" % "C-HC501"   : sensCount ,
	"sensData[%s]" % "T-cpu_emily" : temp_c }

    try:
	response = requests.post(postUrl, data = params)
    except EnvironmentError:
	logger.warning("connection error 1")
	sleep(5)
	try:
	    response = requests.post(postUrl, data = params)
	except EnvironmentError:
	    logger.warning("connection error 2")
	    pass

    logger.debug("response.code = %d" % response.status_code)

######===============================================================#
#
#  Main Module
#
######===============================================================#

logging.basicConfig(format='%(asctime)s %(funcName)s %(message)s', filename='/tmp/p2.log',level=logging.INFO)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())

#
__i2c = smbus.SMBus(1)
ld.init(__i2c)

hsd.init()
m_a.init()
c3_m.init(__i2c)
#
sens_and_record()

m_time = time.time() // 60
s_time = m_time

try:
    while 1:
	time.sleep(0.25)
	hsd.polling()
	m_a.polling()
	c3_m.polling()

	# start Mesurement 2 seconds before every minut
	if (m_time != (time.time() + 2) // 60):
	    m_time = (time.time() + 2) // 60
            logger.debug("main: start measuring [{}]".format(time.time()))
	    (temp_s, temp_c, humidity) = sens_and_record()

	# Send mesured data to the server every minut
	if s_time != (time.time() // 60):
	    s_time = m_time
            logger.debug("main: start posting [{}]".format(time.time()))
	    postToGAE(temp_s, temp_c, humidity, hsd.get_detect_count())

except KeyboardInterrupt:

    ld.display_sw(0)
    GPIO.cleanup()


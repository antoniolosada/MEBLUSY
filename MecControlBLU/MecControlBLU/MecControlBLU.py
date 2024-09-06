#!/usr/bin/python
#
# Simple stuff to control a Meccanoid
#

# Requires:
#  apt-get install python-bluez
#  apt-get install ipython
#  apt-get install python-dev
#  pip install pygatt

from bleak.backends.client import BaseBleakClient
from bleak.backends.service import BleakGATTService
from pygatt.exceptions import NotConnectedError

import bluetooth
import pygatt


import argparse
import asyncio
import time

from bleak import BleakClient, BleakScanner , BleakGATTCharacteristic, Buffer

# ----------------------------------------------------------------------

# The servo IDs, some are unused as yet
UNKNOWN0_SERVO       = 0
RIGHT_ELBOW_SERVO    = 1
RIGHT_SHOULDER_SERVO = 2
LEFT_SHOULDER_SERVO  = 3
LEFT_ELBOW_SERVO     = 4
UNKNOWN5_SERVO       = 5
UNKNOWN6_SERVO       = 6
UNKNOWN7_SERVO       = 7

_servo_lights = \
            [0x0c,
             0x00, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04,
             0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x00]
    
_im_awake =\
        (0x19, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d, 0x1d)    
_servos = \
            [0x08,
             0x7f, 0x80, 0x00, 0xff, 0x80, 0x7f, 0x7f, 0x7f,
             0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01]

_pos_ini_ruedas = (0x0d, 10, 20, 10, 10,
                    0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)
_chest_lights = \
    [0x1c,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

def _cap(value):
    return max(0x00, min(0xff, value))

async def servo(client, servo, value):
        """
        Set a servo value.
        
        The servo numbers are constants in this module.
        The value is between 0x00 and 0xff.
        """

        servo = int(servo)

        if 0 <= servo and servo <= 7:
            # Cap to a byte
            value = _cap(int(value))

            # These guys are reversed, handle that for the user
            if (servo == LEFT_SHOULDER_SERVO or
                servo == RIGHT_ELBOW_SERVO) and value != 0x80:
                value = 0xff - value

            # Set the values
            _servos[servo + 1] = value

        else:
            raise ValueError("Bad servo index: %s" % servo)

        await _send(client, bytes(_servos))
        
async def servo_light(client, servo, value):
    """
    Set the servo light to a given colour.
    """

    if value == 'black' or value == 'off':
        value = 0x00
    elif value == 'red':
        value = 0x01
    elif value == 'green':
        value = 0x02
    elif value == 'yellow':
        value = 0x03
    elif value == 'blue':
        value = 0x04
    elif value == 'magenta':
        value = 0x05
    elif value == 'cyan':
        value = 0x06
    elif value == 'white' or value == 'on':
        value = 0x07
    else:
        raise ValueError('Unknown colour for servo: "%s"' % value)

    if 0 <= servo and servo <= 7:
        _servo_lights[servo + 1] = value

    else:
        raise ValueError("Bad servo index: %s" % servo)

    await _send(client, bytes(_servo_lights))

async def chest_light(client, light, on):
    """
    Set the on/off state of a chest light.

    The light is a value between 0 and 3.
    """

    if 0 <= light and light <= 3:
        if on:
            value = 0x01
        else:
            value = 0x00

        _chest_lights[light + 1] = value
                
    else:
        raise ValueError("Bad light index: %s" % light)

    await _send(client, bytes(_chest_lights))

async def move(client, right_speed=0x00, left_speed=0x00):
    """
    Move the wheels. The speed values are in the range [-255, 255], where a 
    negative value means "backwards".
    """

    # By default do nothing
    right_dir = 0x00
    left_dir  = 0x00

    # Make your move
    if right_speed > 0:
        right_dir   = 0x01
        right_speed = _cap(right_speed)
    else:
        right_dir   = 0x02
        right_speed = _cap(-right_speed)

    if left_speed > 0:
        left_dir   = 0x01
        left_speed = _cap(left_speed)
    else:
        left_dir   = 0x02
        left_speed = _cap(-left_speed)

    # Send the command
    await _send(client, (0x0d, left_dir, right_dir, int(left_speed), int(right_speed),
                0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))


async def eye_lights(client, r, g, b):
    """
    Set the eye lights to a specific colour. RGB values between 0 and 7.
    """

    r = int(min(0x7, max(0x0, r)))
    g = int(min(0x7, max(0x0, g)))
    b = int(min(0x7, max(0x0, b)))

    await _send(client, (0x11, 0x00, 0x00,
                g << 3 | r,
                b,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
        
async def scan():
    address = "CA:BE:84:25:A0:34"
    #devices = await BleakScanner.find_device_by_address(address)
    devices = await BleakScanner.discover()

    for d in devices:
        print(d.name)
        if d.name == "MECCANOID 34A025":
            myDevice = d
            print('Found it')

    client = BleakClient(myDevice)
    await client.connect()

    client.write_gatt_descriptor
    
    #for s in client.services:
    #    print("services: ",s.handle, s.description, s.uuid, s.handle)
    #    for c in s.characteristics:
    #        print("characteristics: ",c.description, c.uuid, c.handle)
    
    #print(client.is_connected())
    await _send(client, _pos_ini_ruedas)
    time.sleep(3)
    await eye_lights(client, 50,120,100)
    time.sleep(3)
    await servo(client, 4, 200)
    time.sleep(2)
    await servo(client, 4, 150)
    time.sleep(2)
    await servo(client, 4, 200)
    time.sleep(3)
    await servo(client, 0, 100)
    time.sleep(2)
    await servo_light(client, 0, 'red')
    time.sleep(3)
    
    for i in range(8):
        await servo_light(client, i, 'green')
    time.sleep(10)
    
async def _send(client, values):
    checksum = 0
    for v in values:
        checksum += v

    payload = tuple(values) + ((checksum >> 8) & 0xff, checksum & 0xff)
    
    await client.write_gatt_char(46,bytes(payload))


        
asyncio.run(scan())



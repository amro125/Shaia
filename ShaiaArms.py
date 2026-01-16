from utils.Dynamixelutils import dynamixel
from dynamixel_sdk import *                    # Uses Dynamixel SDK library
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from typing import List, Any


# Neck tilt 156-210
# HeadTurn 100-260
# headtilt 3) 64-140
# mouth 2) 320-341

dispatcher = Dispatcher()


UP_POSITION = 168 # fixed up position
DOWN_RANGE_0 = [144.7, 137.5] # striker 0: softest -> loudest hit
DOWN_RANGE_1 = [133.3, 127] # striker 1: softest -> loudest hit
STRIKERS_DOWN_RANGE = [DOWN_RANGE_0, DOWN_RANGE_1]

def hit(unused_addr, *args):
    striker_id = args[0]
    volume = args[1] # volume = [0, 1]
    range = STRIKERS_DOWN_RANGE[striker_id]
    down_position = range[0] + volume * (range[1] - range[0])
    strikers[args[0]].hit([down_position, UP_POSITION])

if __name__ == "__main__":
    
    port = '/dev/tty.usbserial-FT62AOPZ'
    port2 = '/dev/tty.usbserial-FT62AODN'
    
    # porthandle1 = PortHandler(port)
    packethandle = PacketHandler(2.0)
    porthandle2 = PortHandler(port2)
    
    numStrikers = 2    
    strikers = []
    for striker in range(numStrikers):
        strikers.append(dynamixel(striker,porthandle2,packethandle,BAUD = 57600))

    dispatcher.map("/hit", hit)

    strikers[0].initmotor()
    # server = BlockingOSCUDPServer(("127.0.0.1", 9000), dispatcher)
    for striker in strikers:
        striker.enable_torque()
        striker.moveto(UP_POSITION,False,100)
        
    try:
        server = BlockingOSCUDPServer(("127.0.0.1", 9010), dispatcher)
        server.serve_forever()  # Blocks forever
    except:
        print("Shutting down...")
        # for striker in strikers:
        #     striker.disable_torque()
        # strikers[0].shutdownSeq()
    finally:
        for striker in strikers:
            striker.disable_torque()
        strikers[0].shutdownSeq()
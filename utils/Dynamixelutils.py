from dynamixel_sdk import * # Uses Dynamixel SDK library
import os
import time

if os.name == 'nt':
    import msvcrt
    def getch():
        return msvcrt.getch().decode()
else:
    import sys, tty, termios
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    def getch():
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch


def degtotick(degree):
    return int(degree * 4095 / 360)
def ticktodeg(tick):
    return int(tick * 360 / 4095)
    
class dynamixel:

    def __init__(self, ID, porthandler, packethandle, BAUD = 57600,):
        self.ID                          = ID  
        self.ADDR_TORQUE_ENABLE          = 64
        self.ADDR_PROFILE_VELOCITY       = 112
        self.ADDR_GOAL_POSITION          = 116
        self.ADDR_PRESENT_POSITION       = 132
        self.DXL_MINIMUM_POSITION_VALUE  = 0         # Refer to the Minimum Position Limit of product eManual
        self.DXL_MAXIMUM_POSITION_VALUE  = 4095      # Refer to the Maximum Position Limit of product eManual
        self.BAUDRATE                    = BAUD
        # self.port                        = port
        self.version                     = 2.0
        self.DXL_MOVING_STATUS_THRESHOLD = 40    # Dynamixel moving status threshold
        self.portHandler = porthandler
        
        self.ADDR_OPERATING_MODE = 11
        self.ADDR_GOAL_CURRENT  = 102
        self.ADDR_POSITION_P_GAIN = 84

        # Initialize PacketHandler instance
        self.packetHandler = packethandle

    def enable_torque(self):
        dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(
        self.portHandler,
        self.ID,
        self.ADDR_TORQUE_ENABLE,
        1)

    def initmotor(self):
        # Initialize PortHandler instance
        # Set the port path
        # Open port
        if self.portHandler.openPort():
            print("Succeeded to open the port")
        else:
            print("Failed to open the port")
            print("Press any key to terminate...")
            getch()
            quit()
        # Set port baudrate
        if self.portHandler.setBaudRate(self.BAUDRATE):
            print("Succeeded to change the baudrate")
        else:
            print("Failed to change the baudrate")
            print("Press any key to terminate...")
            getch()
            quit()

    def set_vel(self, velocity):
        scaledV = int(velocity * 2047)
        dxl_comm_result, dxl_error = self.packetHandler.write4ByteTxRx(
        self.portHandler,
        self.ID,
        self.ADDR_PROFILE_VELOCITY,
        scaledV)
        # self.velocity = velocity  # Instance attribute
    
    def moveto(self, moveto, wait = False, velocity = None, convertToTick = True):
        if convertToTick:
            moveto = degtotick(moveto)
        if velocity is not None:
            self.set_vel(velocity)
            print(f"vel set: {velocity}")
        dxl_comm_result, dxl_error = self.packetHandler.write4ByteTxRx(
        self.portHandler,
        self.ID,
        self.ADDR_GOAL_POSITION,
        moveto)
        if wait:
            self.wait_toStop(moveto)
    
    def wait_toStop(self, moveto):
        check = True
        while check:
            dxl_present_position, dxl_comm_result, dxl_error = self.packetHandler.read4ByteTxRx(
            self.portHandler,
            self.ID,
            self.ADDR_PRESENT_POSITION)
            if abs(moveto - dxl_present_position) < self.DXL_MOVING_STATUS_THRESHOLD:
                check = False
                break
            time.sleep(0.0001)
    
    def disable_torque(self):
        dxl_comm_result, dxl_error = self.packetHandler.write1ByteTxRx(self.portHandler, self.ID, self.ADDR_TORQUE_ENABLE, 0)
        if dxl_comm_result != COMM_SUCCESS:
            print("%s" % self.packetHandler.getTxRxResult(dxl_comm_result))
        elif dxl_error != 0:
            print("%s" % self.packetHandler.getRxPacketError(dxl_error))
    
    def hit(self, hits):
        for hit in hits:
            self.moveto(hit, True, 0.25)

    def shutdownSeq(self):
        # Close port
        self.portHandler.closePort()


    def set_operating_mode(self, mode):
        self.disable_torque()
        self.packetHandler.write1ByteTxRx(
            self.portHandler,
            self.ID,
            self.ADDR_OPERATING_MODE,
            mode
        )
        self.enable_torque()

    def set_goal_current(self, current):
        # current in raw units (XL330: approx 2.69mA per unit)
        self.packetHandler.write2ByteTxRx(
            self.portHandler,
            self.ID,
            self.ADDR_GOAL_CURRENT,
            current
        )

    def set_p_gain(self, p):
        self.packetHandler.write2ByteTxRx(
            self.portHandler,
            self.ID,
            self.ADDR_POSITION_P_GAIN,
            p
        )

    def snapshot_settings(self):
        """Read all relevant registers and store them for later restore"""
        snapshot = {}
        
        # Read operating mode
        mode, _, _ = self.packetHandler.read1ByteTxRx(self.portHandler, self.ID, self.ADDR_OPERATING_MODE)
        snapshot['mode'] = mode
        
        # Read Position P Gain
        p_gain, _, _ = self.packetHandler.read2ByteTxRx(self.portHandler, self.ID, self.ADDR_POSITION_P_GAIN)
        snapshot['p_gain'] = p_gain
        
        # Read Goal Current
        goal_current, _, _ = self.packetHandler.read2ByteTxRx(self.portHandler, self.ID, self.ADDR_GOAL_CURRENT)
        snapshot['goal_current'] = goal_current
        
        # Read Goal Position (for safety / neutral)
        goal_pos, _, _ = self.packetHandler.read4ByteTxRx(self.portHandler, self.ID, self.ADDR_GOAL_POSITION)
        snapshot['goal_position'] = goal_pos

        print(f"Current snapshot for {self.ID}: {snapshot}")
        
        return snapshot
    
    def restore_settings(self, snapshot):
        """Restore previously saved settings"""
        self.disable_torque()
        
        # Restore Operating Mode
        self.packetHandler.write1ByteTxRx(self.portHandler, self.ID, self.ADDR_OPERATING_MODE, snapshot['mode'])
        
        # Restore P Gain
        self.packetHandler.write2ByteTxRx(self.portHandler, self.ID, self.ADDR_POSITION_P_GAIN, snapshot['p_gain'])
        
        # Restore Goal Current
        self.packetHandler.write2ByteTxRx(self.portHandler, self.ID, self.ADDR_GOAL_CURRENT, snapshot['goal_current'])
        
        # Restore Goal Position
        self.packetHandler.write4ByteTxRx(self.portHandler, self.ID, self.ADDR_GOAL_POSITION, snapshot['goal_position'])
        
        self.enable_torque()



    def read_position(self):
        pos, _, _ = self.packetHandler.read4ByteTxRx(
            self.portHandler,
            self.ID,
            self.ADDR_PRESENT_POSITION
        )
        return pos



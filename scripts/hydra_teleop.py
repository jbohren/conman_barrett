#!/usr/bin/env python

import rospy

import sensor_msgs.msg

from lcsr_barrett.wam_teleop import *

"""
analog triggers: gripper analog command

"""

class HydraTeleop(WAMTeleop):

    LEFT = 0
    RIGHT = 1
    TOP_TRIGGER = [10, 11]

    THUMB_X = [0, 2]
    THUMB_Y = [1, 3]
    THUMB_CLICK = [1, 2]

    BOT_TRIGGER = [8, 9]

    B_CENTER = [0, 3]
    B1 = [7, 15]
    B2 = [6, 14]
    B3 = [5, 13]
    B4 = [4, 12]

    SIDE_STR = ['left', 'right']
    SIDE_MAP = {'left': LEFT, 'right': RIGHT}

    def __init__(self):

        # Get WAMTeleop params
        self.side = self.SIDE_MAP.get(rospy.get_param("~side",''), self.RIGHT)
        input_ref_frame_id = rospy.get_param('~ref_frame', '/hydra_base')
        input_frame_id = rospy.get_param('~input_frame', '/hydra_'+self.SIDE_STR[self.side]+'_grab')
        super(HydraTeleop, self).__init__(input_ref_frame_id, input_frame_id)

        # Get the clutch button
        # This is the (0-based) index of the button in the clutch joy topic
        self.deadman_button = rospy.get_param('~deadman_button', None)
        self.resync_button = rospy.get_param('~resync_button', None)

        # Get the clutch duration
        # This is the time over which the cart command scale is increased
        self.clutch_duration = rospy.get_param('~clutch_duration', 0.3)

        self.gripper_min = 1.0
        self.gripper_max = 0.0

        # Button state
        self.last_buttons = [0] * 16
        self.clutch_enabled = False
        self.deadman_enable_time = None

        self.resync_engaged = False

        self.cart_scale = None
        self.last_joy_cmd = rospy.Time.now()

        # Hydra Joy input
        self.joy_sub = rospy.Subscriber('hydra_joy', sensor_msgs.msg.Joy, self.joy_cb)
        self.clutch_sub = rospy.Subscriber('clutch_joy', sensor_msgs.msg.Joy, self.clutch_cb)

    def clutch_cb(self, msg):
        """Handle clutch joy messages."""

        # If the deadman_button isn't set, then assume it's the first button pressed after startup

        if self.deadman_button is None or self.resync_button is None:
            if msg.buttons.count(1) == 1:
                try:
                    button_index = msg.buttons.index(1)
                except ValueError:
                    return
                if self.deadman_button is None:
                    rospy.loginfo("Using clutch button {} for deadman.".format(button_index))
                    self.deadman_button = button_index
                elif self.resync_button is None and button_index != self.deadman_button:
                    rospy.loginfo("Using clutch button {} for resync.".format(button_index))
                    self.resync_button = button_index
            return

        # Get the current deadman and resync state
        clutch_enabled_now = msg.buttons[self.deadman_button]
        self.resync_engaged = msg.buttons[self.resync_button]

        if self.clutch_enabled != clutch_enabled_now:
            # The clutch has changed mode
            if clutch_enabled_now:
                # The clutch has been enabled
                self.deadman_enable_time = rospy.Time.now()
            else:
                # The clutch has been disabled, so stop the hand
                self.hand_cmd.mode = [oro_barrett_msgs.msg.BHandCmd.MODE_VELOCITY] * 4
                self.hand_cmd.cmd = [0.0, 0.0, 0.0, 0.0]
                self.hand_pub.publish(self.hand_cmd)
                self.last_hand_cmd = rospy.Time.now()
                self.deadman_engaged = False

        # Update the clutch value
        self.clutch_enabled = clutch_enabled_now

    def joy_cb(self, msg):
        """Generate a cart/hand cmd from a hydra joy message"""

        # Convenience
        side = self.side
        b = msg.buttons
        lb = self.last_buttons

        self.check_for_backwards_time_jump()

        # Get gripper range
        gripper_val = msg.axes[self.BOT_TRIGGER[side]]
        self.gripper_min = min(self.gripper_min, gripper_val)
        self.gripper_max = max(self.gripper_max, gripper_val)

        # Do nothing until gripper range has been established
        if self.gripper_max < self.gripper_min or abs(self.gripper_min - self.gripper_max) < 0.5:
            rospy.logwarn("Trigger has not yet been calibrated, please move it through it's entire range")
            rospy.logwarn("{} <= {} <= {}".format(self.gripper_min, gripper_val, self.gripper_max))
            return

        normalized_gripper_val = (gripper_val - self.gripper_min) / (self.gripper_max - 0.04)
        normalized_gripper_val = max(0.0, min(normalized_gripper_val, 1.0))
        rospy.logdebug("grasp {} => {} ({}, {})".format(gripper_val, normalized_gripper_val,self.gripper_min, self.gripper_max))

        if msg.header.stamp - self.last_joy_cmd < rospy.Duration(0.03):
            self.last_joy_cmd = msg.header.stamp
            return

        if (rospy.Time.now() - self.last_hand_cmd) < rospy.Duration(0.03):
            return

        # Update enabled fingers
        if 0:
            self.move_f[0] =   self.move_f[0] ^   (b[self.B1[side]] and not lb[self.B1[side]])
            self.move_f[1] =   self.move_f[1] ^   (b[self.B2[side]] and not lb[self.B2[side]])
            self.move_f[2] =   self.move_f[2] ^   (b[self.B3[side]] and not lb[self.B3[side]])
            self.move_spread = self.move_spread ^ (b[self.B4[side]] and not lb[self.B4[side]])
            self.move_all =    self.move_all ^    (b[self.B_CENTER[side]] and not lb[self.B_CENTER[side]])

        # Check if the deadman is engaged
        if self.clutch_enabled:
            reset_to_tip = not b[self.B_CENTER[side]]
            if reset_to_tip:
                self.cart_scale = min(1.0, (rospy.Time.now() - self.deadman_enable_time).to_sec() / self.clutch_duration)
            else:
                self.cart_scale = 1.0
            self.handle_hand_cmd(msg.axes[self.BOT_TRIGGER[side]], msg.axes[self.THUMB_X[side]])
            self.handle_cart_cmd(self.cart_scale, reset_to_tip)

        # Update last raw command values
        self.last_buttons = msg.buttons
        self.last_axes = msg.axes

        # Broadcast the command if it's defined
        self.resync_pose = self.resync_engaged #msg.buttons[self.B_CENTER[side]]
        self.augmenter_engaged = msg.buttons[self.TOP_TRIGGER[side]] == 1
        grasp_opening = (1.0 - (0.25 + 0.75*pow(normalized_gripper_val,2)))
        self.publish_cmd(self.resync_pose, self.augmenter_engaged, grasp_opening, msg.header.stamp)

        # republish markers
        self.publish_cmd_ring_markers(msg.header.stamp)


def main():
    rospy.init_node('hydra_teleop')

    ht = HydraTeleop()

    rospy.spin()

if __name__ == '__main__':
    main()

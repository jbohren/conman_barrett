
--[[ get ROS global service --]]
depl:import("rtt_ros")
ros = gs:provides("ros")
ros:import("lcsr_barrett")

--[ Set log-level ]--
rtt.setLogLevel("Warning")

--[[ add lua dir to the lua path --]]
package.path = ros:find("lcsr_barrett") .. "/lua/?.lua" .. ";" .. package.path

require("lcsr_barrett")
lcsr_barrett(true,"w2","/wam2/robot_description")

--[[ Start the WAM --]]
barrett_manager:provides("wam"):initialize()
barrett_manager:provides("wam"):run()

--[[ Start the hand --]]
if barrett_manager:getProperty("auto_configure_hand"):get() then
  rtt.log("Running hand...")
  barrett_manager:provides("hand"):run()
  barrett_manager:provides("hand"):open()
else
  rtt.log("No hands!")
end

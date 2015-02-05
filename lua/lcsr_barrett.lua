
--[[ add lua dir to the lua path --]]
--package.path = ros:find("lcsr_barrett") .. "/lua/?.lua" .. ";" .. package.path

function lcsr_barrett(sim, prefix, urdf_param)
  --[[ defaulat args --]]
  local sim = sim or false
  local prefix = prefix or ""
  local urdf_param = urdf_param or "/robot_description"

  --[[ get ROS global service --]]
  depl:import("rtt_ros")
  ros = gs:provides("ros")
  ros:import("lcsr_barrett")

  --[[ set up TF component -]]
  depl:import("rtt_tf")
  depl:loadComponent("tf","rtt_tf::RTT_TF")
  tf = depl:getPeer("tf")
  tf:configure()
  tf:start()

  --[[ create conman scheme --]]
  scheme_name = prefix.."scheme"
  depl:loadComponent(scheme_name,"conman::Scheme")
  scheme = depl:getPeer(scheme_name)
  if sim then
    scheme:setPeriod(0.001)
    scheme:loadService("sim_clock_activity");
  else
    depl:setActivity(
      scheme:getName(),
      0.001,
      depl:getAttribute("HighestPriority"):get(),
      rtt.globals.ORO_SCHED_RT)
  end
  scheme:loadService("conman_ros");
  scheme:configure();

  --[[ Load barrett manager, wam --]]
  rtt.log("Loading barret...")
  require("load_barrett")
  manager, effort_sum = load_barrett(depl, scheme, prefix, sim, urdf_param)
  if not manager then
    rtt.logl("Error", "Failed to create barrett manager, is the WAM plugged in and is the CANBus properly configured?");
    return false;
  end

  --[[ Load controllers --]]
  require("load_controllers")
  load_controllers(depl, scheme, prefix);

  --[[ Start the Scheme --]]
  scheme:start();

  --[[ Set of initially running blocks --]]
  scheme:enableBlock(prefix.."devices",true);
  scheme:enableBlock(prefix.."joint_control",true);
  --scheme.enableBlock("cart_imp_control",true);
end

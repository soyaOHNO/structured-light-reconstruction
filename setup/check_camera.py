import PySpin

system = PySpin.System.GetInstance()
cameras = None
try:
    cameras = system.GetCameras()
    print(f"Camera count: {cameras.GetSize()}")
    for index in range(cameras.GetSize()):
        camera = cameras.GetByIndex(index)
        try:
            info = camera.GetTLDeviceNodeMap()
            model = PySpin.CStringPtr(info.GetNode("DeviceModelName"))
            serial = PySpin.CStringPtr(info.GetNode("DeviceSerialNumber"))
            print(f"Model: {model.GetValue()}")
            print(f"Serial: {serial.GetValue()}")
        finally:
            del camera
finally:
    if cameras is not None:
        cameras.Clear()
    system.ReleaseInstance()
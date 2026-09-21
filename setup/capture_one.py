from datetime import datetime
from pathlib import Path

import PySpin


def main():
    output_dir = Path(__file__).resolve().parent / "captures"
    output_dir.mkdir(exist_ok=True)

    system = PySpin.System.GetInstance()
    cameras = None
    camera = None
    image = None
    initialized = False
    acquiring = False

    try:
        cameras = system.GetCameras()
        if cameras.GetSize() != 1:
            raise RuntimeError(
                f"Expected 1 camera, found {cameras.GetSize()}"
            )

        camera = cameras.GetByIndex(0)
        camera.Init()
        initialized = True

        # Start acquisition without an external trigger.
        camera.TriggerMode.SetValue(PySpin.TriggerMode_Off)
        camera.AcquisitionMode.SetValue(
            PySpin.AcquisitionMode_Continuous
        )

        camera.BeginAcquisition()
        acquiring = True

        image = camera.GetNextImage(5000)

        if image.IsIncomplete():
            raise RuntimeError(
                f"Incomplete image: status={image.GetImageStatus()}"
            )

        # Convert the color image to RGB8 for PNG output.
        processor = PySpin.ImageProcessor()
        processor.SetColorProcessing(
            PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR
        )
        converted = processor.Convert(image, PySpin.PixelFormat_RGB8)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_path = output_dir / f"capture_{timestamp}.png"
        converted.Save(str(output_path))

        print(f"Saved: {output_path}")
        print(f"Size: {image.GetWidth()} x {image.GetHeight()}")

    finally:
        if image is not None:
            image.Release()

        try:
            if acquiring:
                camera.EndAcquisition()
        finally:
            try:
                if initialized:
                    camera.DeInit()
            finally:
                camera = None
                if cameras is not None:
                    cameras.Clear()
                system.ReleaseInstance()


if __name__ == "__main__":
    main()
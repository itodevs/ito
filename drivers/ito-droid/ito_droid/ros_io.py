"""ROS-facing camera and servo adapters for Ito Droid."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable, Protocol

from .config import ItoDroidConfig

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraFrame:
    data: bytes
    received_at_seconds: float
    encoding: str | None = None
    width: int | None = None
    height: int | None = None


class CameraFrameSink(Protocol):
    def receive_camera_frame(self, frame: CameraFrame) -> None:
        ...


class ServoPublisher(Protocol):
    def publish_angle(self, angle_degrees: float) -> None:
        ...


class LoggingServoPublisher:
    def publish_angle(self, angle_degrees: float) -> None:
        LOGGER.info("camera_pan_servo %.3f", angle_degrees)


class RosBridge:
    """Small ROS adapter kept outside the Ito protocol and control core."""

    def __init__(
        self,
        config: ItoDroidConfig,
        frame_sink: CameraFrameSink,
        *,
        clock: Callable[[], float],
    ) -> None:
        self.config = config
        self.frame_sink = frame_sink
        self.clock = clock
        self._rclpy = None
        self._node = None
        self._servo_publisher = None

    def start(self) -> None:
        try:
            import rclpy
            from sensor_msgs.msg import Image
            from std_msgs.msg import Float64
        except ImportError as exc:
            raise RuntimeError("ROS Python packages are required to run Ito Droid on robot") from exc

        self._rclpy = rclpy
        rclpy.init(args=None)
        self._node = rclpy.create_node(self.config.ros_node_name)
        self._servo_publisher = self._node.create_publisher(
            Float64,
            self.config.ros_servo_command_topic,
            10,
        )
        self._node.create_subscription(Image, self.config.ros_camera_topic, self._handle_image, 10)

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        if self._rclpy is not None and self._node is not None:
            self._rclpy.spin_once(self._node, timeout_sec=timeout_seconds)

    def publish_angle(self, angle_degrees: float) -> None:
        if self._servo_publisher is None:
            raise RuntimeError("ROS servo publisher is not started")
        from std_msgs.msg import Float64

        msg = Float64()
        msg.data = float(angle_degrees)
        self._servo_publisher.publish(msg)

    def close(self) -> None:
        if self._node is not None:
            self._node.destroy_node()
        if self._rclpy is not None:
            self._rclpy.shutdown()
        self._node = None
        self._rclpy = None
        self._servo_publisher = None

    def _handle_image(self, msg: object) -> None:
        data = bytes(getattr(msg, "data", b""))
        frame = CameraFrame(
            data=data,
            received_at_seconds=self.clock(),
            encoding=getattr(msg, "encoding", None),
            width=getattr(msg, "width", None),
            height=getattr(msg, "height", None),
        )
        self.frame_sink.receive_camera_frame(frame)


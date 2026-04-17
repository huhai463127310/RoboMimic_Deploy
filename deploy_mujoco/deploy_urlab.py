import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from common.path_config import PROJECT_ROOT

import time
import threading
import numpy as np
import yaml
import os
import struct
import json
import zmq
from datetime import datetime
from common.ctrlcomp import *
from FSM.FSM import *
from common.utils import get_gravity_orientation
from common.joystick import JoyStick, JoystickButton
from pynput import keyboard as pynput_keyboard

# 设置日志同时输出到控制台和文件
class TeeLogger:
    """同时将输出重定向到控制台和文件的类"""
    def __init__(self, filename, mode='a'):
        self.file = open(filename, mode, encoding='utf-8')
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        
    def write(self, data):
        self.stdout.write(data)
        self.file.write(data)
        self.file.flush()
        
    def flush(self):
        self.stdout.flush()
        self.file.flush()
        
    def close(self):
        self.file.close()

# 创建日志文件路径
log_dir = Path(PROJECT_ROOT) / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"deploy_urlab_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# 重定向输出
sys.stdout = TeeLogger(str(log_file), 'w')
sys.stderr = sys.stdout

print(f"[URLab] Logging to: {log_file}")


class Keyboard:
    """键盘输入类，使用 pynput 全局监听键盘"""
    def __init__(self):
        self.key_states = {}
        self.key_prev_states = {}
        self.key_pressed_events = {}
        self.key_released_events = {}
        self._listener = None
        self._lock = threading.Lock()
        
        # 键名映射
        self.key_map = {
            '1': '1', '2': '2', '3': '3', '4': '4', '5': '5',
            '6': '6', '7': '7', '8': '8', '9': '9', '0': '0',
            'NUMPAD1': 'num1', 'NUMPAD2': 'num2', 'NUMPAD3': 'num3',
            'NUMPAD4': 'num4', 'NUMPAD5': 'num5', 'NUMPAD6': 'num6',
            'NUMPAD7': 'num7', 'NUMPAD8': 'num8', 'NUMPAD9': 'num9', 'NUMPAD0': 'num0',
            'F1': 'f1', 'F2': 'f2', 'F3': 'f3', 'F4': 'f4', 'F5': 'f5',
            'A': 'a', 'B': 'b', 'C': 'c', 'D': 'd', 'E': 'e',
            'F': 'f', 'G': 'g', 'H': 'h', 'I': 'i', 'J': 'j',
            'K': 'k', 'L': 'l', 'M': 'm', 'N': 'n', 'O': 'o',
            'P': 'p', 'Q': 'q', 'R': 'r', 'S': 's', 'T': 't',
            'U': 'u', 'V': 'v', 'W': 'w', 'X': 'x', 'Y': 'y', 'Z': 'z',
            'SPACE': 'space',
            'ESCAPE': 'esc',
            'ENTER': 'enter',
            'TAB': 'tab',
            'BACKSPACE': 'backspace',
            'LSHIFT': 'shift', 'RSHIFT': 'shift',
            'LCTRL': 'ctrl_l', 'RCTRL': 'ctrl_r',
            'LALT': 'alt_l', 'RALT': 'alt_r',
            'UP': 'up', 'DOWN': 'down', 'LEFT': 'left', 'RIGHT': 'right',
        }
        
        # 启动键盘监听
        self._start_listener()
    
    def _start_listener(self):
        """启动键盘监听器"""
        def on_press(key):
            try:
                # 处理小键盘数字 (Key.np0 ~ Key.np9 或 <96>~<105>)
                k_str = str(key)
                k = None
                
                # 检查k_str是否为字符串
                if not isinstance(k_str, str):
                    return
                
                if 'np' in k_str or (k_str.startswith('<') and k_str.endswith('>')):
                    # 小键盘数字: <96>=np0, <97>=np1, ... <105>=np9
                    try:
                        num = int(k_str.strip('<>')) - 96
                        if 0 <= num <= 9:
                            k = f'num{num}'
                        else:
                            k = k_str.lower()
                    except:
                        k = k_str.replace('Key.', '').lower()
                elif hasattr(key, 'char') and key.char and isinstance(key.char, str):
                    # 字符键 (包括Shift+数字产生的!@#$%^&*())
                    k = key.char.lower()
                else:
                    k = str(key).replace('Key.', '').lower()
                
                # 确保k是字符串
                if k is None or not isinstance(k, str):
                    return
                
                with self._lock:
                    self.key_states[k] = True
                print(f"[Keyboard] Key pressed: {k}")
            except Exception as e:
                print(f"[Keyboard] Error on press: {e}")
        
        def on_release(key):
            try:
                k_str = str(key)
                k = None
                
                # 检查k_str是否为字符串
                if not isinstance(k_str, str):
                    return
                
                if 'np' in k_str or (k_str.startswith('<') and k_str.endswith('>')):
                    try:
                        num = int(k_str.strip('<>')) - 96
                        if 0 <= num <= 9:
                            k = f'num{num}'
                        else:
                            k = k_str.lower()
                    except:
                        k = k_str.replace('Key.', '').lower()
                elif hasattr(key, 'char') and key.char and isinstance(key.char, str):
                    k = key.char.lower()
                else:
                    k = str(key).replace('Key.', '').lower()
                
                # 确保k是字符串
                if k is None or not isinstance(k, str):
                    return
                
                with self._lock:
                    self.key_states[k] = False
                print(f"[Keyboard] Key released: {k}")
            except Exception as e:
                print(f"[Keyboard] Error on release: {e}")
        
        self._listener = pynput_keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()
    
    def stop(self):
        """停止键盘监听"""
        if self._listener:
            try:
                self._listener.stop()
                # 等待最多0.5秒让线程终止，避免阻塞
                if self._listener.is_alive():
                    self._listener.join(timeout=0.5)
            except Exception as e:
                print(f"[Keyboard] Error stopping: {e}")

    def update(self):
        """更新键盘状态（每帧调用）"""
        try:
            with self._lock:
                self.key_pressed_events.clear()
                self.key_released_events.clear()
                
                # 处理key_map中的键
                for key_name, key_char in self.key_map.items():
                    # 跳过非字符串的key_char
                    if not isinstance(key_char, str):
                        continue
                    current = self.key_states.get(key_char, False)
                    prev = self.key_prev_states.get(key_char, False)
                    
                    # 确保是布尔值，不是数组
                    if isinstance(current, np.ndarray):
                        current = bool(current.any())
                    if isinstance(prev, np.ndarray):
                        prev = bool(prev.any())
                    current = bool(current)
                    prev = bool(prev)
                    
                    if current and not prev:
                        self.key_pressed_events[key_name] = True
                    if not current and prev:
                        self.key_released_events[key_name] = True
                    
                    self.key_prev_states[key_char] = current
                
                # 处理所有在key_states中但不在key_map中的键（如符号键!@#$%）
                mapped_chars = set(self.key_map.values())
                for key_char in list(self.key_states.keys()):
                    # 跳过非字符串的key
                    if not isinstance(key_char, str):
                        continue
                    if key_char not in mapped_chars:
                        current = self.key_states.get(key_char, False)
                        prev = self.key_prev_states.get(key_char, False)
                        
                        # 确保是布尔值，不是数组
                        if isinstance(current, np.ndarray):
                            current = bool(current.any())
                        if isinstance(prev, np.ndarray):
                            prev = bool(prev.any())
                        current = bool(current)
                        prev = bool(prev)
                        
                        if current and not prev:
                            self.key_pressed_events[key_char] = True
                        if not current and prev:
                            self.key_released_events[key_char] = True
                        
                        self.key_prev_states[key_char] = current
        except Exception as e:
            import traceback
            print(f"[Keyboard] Error in update: {e}")
            traceback.print_exc()

    def is_key_pressed(self, key):
        """检测按键是否按下"""
        if not isinstance(key, str):
            return False
        key_char = self.key_map.get(key, key.lower())
        with self._lock:
            val = self.key_states.get(key_char, False)
            # 确保返回标量布尔值，不是数组
            if isinstance(val, np.ndarray):
                return bool(val.any())
            return bool(val)

    def is_key_released(self, key):
        """检测按键是否释放（刚松开）"""
        if not isinstance(key, str):
            return False
        # 直接检查key_released_events，支持原始键名（包括符号键如!@#$）
        key_lower = key.lower()
        # 检查key_map映射后的名称、原始键名（大写）和原始键名（小写）
        mapped_key = self.key_map.get(key, key_lower)
        
        # 获取值并确保是标量布尔值
        val1 = self.key_released_events.get(key, False)
        val2 = self.key_released_events.get(mapped_key, False)
        val3 = self.key_released_events.get(key_lower, False)
        
        # 转换为标量布尔值
        def to_bool(v):
            if isinstance(v, np.ndarray):
                return bool(v.any())
            return bool(v)
        
        return to_bool(val1) or to_bool(val2) or to_bool(val3)

    def is_key_just_pressed(self, key):
        """检测按键是否刚按下"""
        return self.key_pressed_events.get(key, False)

    def get_axis_from_keys(self, neg_key, pos_key):
        """从两个按键获取轴值（-1 到 1）"""
        neg = self.is_key_pressed(neg_key)
        pos = self.is_key_pressed(pos_key)
        if neg and pos:
            return 0.0
        elif neg:
            return -1.0
        elif pos:
            return 1.0
        return 0.0


class URLabBridge:
    """URLab Bridge - 通过 ZMQ 将策略数据发送到 Unreal Engine"""
    def __init__(self, prefix="g1", state_ep="tcp://127.0.0.1:5555", ctrl_ep="tcp://127.0.0.1:5556", info_ep="tcp://127.0.0.1:5557"):
        self.prefix = prefix
        self.state_ep = state_ep
        self.ctrl_ep = ctrl_ep
        self.info_ep = info_ep
        self._pub_connected = False
        self._sub_connected = False
        self._first_msg_received = False
        self._actuator_ids = None  # 从UE获取的actuator ID映射
        self._joint_names = None  # 从UE获取的关节名称列表
        
        # ZMQ 上下文和套接字
        self.ctx = zmq.Context()
        
        # SUB socket: 接收来自 UE 的传感器数据 (connect to UE's PUB socket)
        # UE binds PUB to state_ep, we connect SUB to receive sensor data
        self.sub = None
        if state_ep:
            self.sub = self.ctx.socket(zmq.SUB)
            try:
                self.sub.connect(state_ep)
                self._sub_connected = True
                self.sub.setsockopt_string(zmq.SUBSCRIBE, "")
                self.sub.setsockopt(zmq.RCVTIMEO, 1)  # 非阻塞接收
                print(f"[URLabBridge] SUB connected to {state_ep} (receive sensor data from UE)")
            except zmq.ZMQError as e:
                print(f"[URLabBridge] Warning: SUB connect failed: {e}")
                self.sub.close()
                self.sub = None
        
        # 尝试从info endpoint获取actuator ID映射
        self._discover_actuator_ids()
        
        # PUB socket: 发送控制命令到 UE (connect to UE's SUB socket)
        # UE binds SUB to ctrl_ep, we connect PUB to send control commands
        self.pub = self.ctx.socket(zmq.PUB)
        try:
            self.pub.connect(ctrl_ep)
            self._pub_connected = True
            # 设置发送超时，防止阻塞
            self.pub.setsockopt(zmq.SNDTIMEO, 1000)  # 1秒发送超时
            print(f"[URLabBridge] PUB connected to {ctrl_ep} (send control to UE)")
            # 等待ZMQ连接建立（slow joiner问题）
            time.sleep(0.5)
        except zmq.ZMQError as e:
            print(f"[URLabBridge] Warning: PUB connect failed: {e}")
        
        print(f"[URLabBridge] Initialized: prefix={prefix}")
        print(f"[URLabBridge] Waiting for UE...")
    
    def _discover_actuator_ids(self):
        """从UE info endpoint获取actuator ID映射"""
        if not self.info_ep:
            return
        try:
            socket = self.ctx.socket(zmq.REQ)
            socket.setsockopt(zmq.RCVTIMEO, 2000)  # 2秒超时
            socket.connect(self.info_ep)
            socket.send_string("get_actuator_info")
            response = socket.recv_json()
            socket.close()
            
            if "actuator_ids" in response:
                self._actuator_ids = response["actuator_ids"]
                print(f"[URLabBridge] Discovered {len(self._actuator_ids)} actuator IDs from UE")
            if "joint_names" in response:
                self._joint_names = response["joint_names"]
                print(f"[URLabBridge] Joint names: {self._joint_names[:5]}... (total {len(self._joint_names)})")
        except Exception as e:
            print(f"[URLabBridge] Warning: Failed to discover actuator IDs: {e}")
            print(f"[URLabBridge] Will use default sequential IDs (0, 1, 2, ...)")
    
    def check_connection(self):
        """检查ZMQ连接状态，返回是否至少有一个通道就绪"""
        return self._pub_connected
    
    def test_connection(self, timeout_sec=10):
        """
        测试与UE的连接，打印接收到的关节数据
        参考 URLab_Bridge 的 _test_connection 实现
        """
        if not self._sub_connected or self.sub is None:
            print(f"[URLabBridge] No SUB connection, cannot test")
            return False
        
        print(f"[URLabBridge] Testing connection for {timeout_sec}s...")
        print(f"[URLabBridge] Waiting for data from UE on {self.ctrl_ep}")
        
        # 临时设置更长的超时
        orig_timeout = self.sub.getsockopt(zmq.RCVTIMEO)
        self.sub.setsockopt(zmq.RCVTIMEO, 5000)  # 5秒超时
        
        count = 0
        start = time.time()
        try:
            while time.time() - start < timeout_sec:
                try:
                    topic = self.sub.recv_string()
                    if self.sub.getsockopt(zmq.RCVMORE):
                        payload = self.sub.recv()
                        if "/twist" in topic and len(payload) == 12:
                            vx, vy, vyaw = struct.unpack("<fff", payload)
                            print(f"  [{topic}] vx:{vx:.3f} vy:{vy:.3f} vyaw:{vyaw:.3f}")
                            count += 1
                        elif "/joint/" in topic and len(payload) == 16:
                            jid, p, v, a = struct.unpack("<Ifff", payload)
                            print(f"  [{topic}] ID:{jid} Pos:{p:.3f} Vel:{v:.3f}")
                            count += 1
                except zmq.Again:
                    if count == 0:
                        print(f"[URLabBridge] No data yet... (waiting for UE)")
        except KeyboardInterrupt:
            pass
        finally:
            self.sub.setsockopt(zmq.RCVTIMEO, orig_timeout)
        
        print(f"[URLabBridge] Test complete: received {count} messages in {time.time()-start:.1f}s")
        return count > 0
    
    def send_joint_states(self, joint_positions, joint_velocities=None):
        """
        发送关节状态（控制命令）到 Unreal Engine
        通过 PUB socket 发送到 UE 的 ControlSubscriber
        Topic格式: {prefix}/control
        
        Args:
            joint_positions: 关节位置数组 (num_joints,)
            joint_velocities: 关节速度数组 (num_joints,)，可选
        
        Returns:
            bool: 是否成功发送
        """
        if not self._pub_connected or self.pub is None:
            if not hasattr(self, '_pub_error_printed'):
                print(f"[URLabBridge] Error: PUB not connected, cannot send")
                self._pub_error_printed = True
            return False
            
        if joint_velocities is None:
            joint_velocities = np.zeros_like(joint_positions)
        
        num_joints = len(joint_positions)
        
        # 构建topic: prefix/control （注意末尾有空格！）
        topic = f"{self.prefix}/control "
        
        # 构建payload: 匹配URLab_Bridge格式
        # 格式: N(int32) + [actuator_id(int32) + target_position(float32)] * N
        # 总大小: 4 + N * 8 字节
        # 构建格式字符串: <i + (if)*N = N + N个(id+pos)对
        fmt = "<i" + "if" * num_joints  # i=N, 然后是N个(id, pos)对
        flat_data = [num_joints]
        
        # 使用正确的actuator ID（从UE获取的映射，或默认顺序）
        actuator_ids = self._actuator_ids if self._actuator_ids is not None else list(range(num_joints))
        
        for i in range(num_joints):
            aid = actuator_ids[i] if i < len(actuator_ids) else i  # actuator ID
            flat_data.append(aid)
            flat_data.append(float(joint_positions[i]))  # target position
        payload = struct.pack(fmt, *flat_data)
        
        try:
            # 使用 multipart 发送：topic + payload
            self.pub.send_multipart([topic.encode('utf-8'), payload], zmq.NOBLOCK)
            
            # 调试输出
            import time
            current_time = time.time()
            if not hasattr(self, '_frame_count'):
                self._frame_count = 0
                self._send_count = 0
                self._last_print_time = current_time
                self._last_print_count = 0
            self._frame_count += 1
            self._send_count += 1
            
            # 每次发送都打印所有关节数据
            actuator_ids = self._actuator_ids if self._actuator_ids is not None else list(range(num_joints))
            joint_names = self._joint_names if self._joint_names is not None else [f"joint_{i}" for i in range(num_joints)]
            detail_str = " | ".join([
                f"{actuator_ids[i] if i < len(actuator_ids) else i}:{joint_names[i] if i < len(joint_names) else f'joint_{i}'}={joint_positions[i]:6.3f}"
                for i in range(num_joints)
            ])
            print(f"[URLabBridge] Send[{self._send_count:4d}] {topic}: {detail_str}")
            
            # 每100帧打印一次完整调试信息（包含频率）
            if self._frame_count % 100 == 0:
                # 每100帧打印一次调试信息，包含频率
                elapsed = current_time - self._last_print_time
                count_diff = self._send_count - self._last_print_count
                freq = count_diff / elapsed if elapsed > 0 else 0
                print(f"[URLabBridge] Frame {self._frame_count}: sent {self._send_count} packets, Freq={freq:.1f}Hz, Topic={topic}, Pos={joint_positions[:3].round(3)}")
                self._last_print_time = current_time
                self._last_print_count = self._send_count
            
            return True
            
        except zmq.Again:
            print(f"[URLabBridge] Warning: send queue full")
            return False
        except zmq.ZMQError as e:
            print(f"[URLabBridge] ZMQ Error: {e}")
            return False
    
    def send_gains(self, kps, kds, torque_limits=None, joint_names=None):
        """
        发送PD增益参数到UE（用于motor模式的PD控制）
        Topic: {prefix}/set_gains （末尾有空格）
        Payload: JSON字符串
        
        Args:
            kps: 关节kp数组 (num_joints,)
            kds: 关节kd数组 (num_joints,)
            torque_limits: 力矩限制数组，可选
            joint_names: 关节名称列表，可选（默认使用joint_0, joint_1等）
        """
        if not self._pub_connected or self.pub is None:
            return False
        
        num_joints = len(kps)
        if joint_names is None:
            # 使用默认关节名（与XML中的motor名称对应）
            joint_names = [f"joint_{i}" for i in range(num_joints)]
        if torque_limits is None:
            torque_limits = [200.0] * num_joints  # 默认200Nm限制
        
        # 构建JSON payload
        gains_dict = {}
        for i, name in enumerate(joint_names):
            gains_dict[name] = {
                "kp": float(kps[i]),
                "kv": float(kds[i]),
                "torque_limit": float(torque_limits[i])
            }
        
        topic = f"{self.prefix}/set_gains "
        payload = json.dumps(gains_dict).encode('utf-8')
        
        try:
            self.pub.send_multipart([topic.encode('utf-8'), payload], zmq.NOBLOCK)
            print(f"[URLabBridge] Gains sent: {num_joints} joints, payload={len(payload)} bytes")
            return True
        except zmq.ZMQError as e:
            print(f"[URLabBridge] Error sending gains: {e}")
            return False
    
    def recv_ue_data(self):
        """
        接收所有来自 UE 的传感器数据（非阻塞）
        包括: /joint/{name}, /sensor/{name}, /twist 等
        
        Returns:
            dict: 包含所有接收到的数据，或空字典表示无新数据
        """
        if self.sub is None or not self._sub_connected:
            return {}
        
        data = {
            'joint_pos': {},      # {joint_name: position}
            'joint_vel': {},      # {joint_name: velocity}
            'sensors': {},        # {sensor_name: values_array}
            'twist': None,        # [vx, vy, vyaw]
        }
        
        # 非阻塞接收所有可用消息
        max_msgs = 100  # 每帧最多处理100条消息
        for _ in range(max_msgs):
            try:
                topic = self.sub.recv_string(zmq.NOBLOCK)
                if not self.sub.getsockopt(zmq.RCVMORE):
                    continue
                    
                payload = self.sub.recv(zmq.NOBLOCK)
                
                # 首次收到消息时提取prefix
                if not self._first_msg_received:
                    if "/" in topic:
                        actual_prefix = topic.split("/")[0]
                        if actual_prefix != self.prefix:
                            print(f"[URLabBridge] Updating prefix: {self.prefix} -> {actual_prefix}")
                            self.prefix = actual_prefix
                    self._first_msg_received = True
                
                # 解析不同类型的消息
                parts = topic.split("/")
                if len(parts) < 2:
                    continue
                
                data_type = parts[1] if len(parts) > 1 else ""
                
                if data_type == "joint" and len(parts) >= 3:
                    # {prefix}/joint/{JointName}: <Ifff = ID, pos, vel, acc
                    if len(payload) == 16:
                        jid, pos, vel, acc = struct.unpack("<Ifff", payload)
                        joint_name = parts[2]
                        data['joint_pos'][joint_name] = pos
                        data['joint_vel'][joint_name] = vel
                        
                elif data_type == "sensor" and len(parts) >= 3:
                    # {prefix}/sensor/{SensorName}: <II + float*dim
                    if len(payload) >= 8:
                        sid, dim = struct.unpack("<II", payload[:8])
                        expected_len = 8 + dim * 4
                        if len(payload) == expected_len:
                            values = struct.unpack(f"<{dim}f", payload[8:])
                            sensor_name = parts[2]
                            data['sensors'][sensor_name] = np.array(values, dtype=np.float32)
                            
                elif data_type == "twist":
                    # {prefix}/twist: <fff = vx, vy, vyaw
                    if len(payload) == 12:
                        vx, vy, vyaw = struct.unpack("<fff", payload)
                        data['twist'] = np.array([vx, vy, vyaw], dtype=np.float32)
                        
                elif data_type == "base_state" and len(parts) >= 3:
                    # {prefix}/base_state/{JointName}: 7 x float64 (pos xyz + quat wxyz)
                    if len(payload) == 7 * 8:  # 7 doubles
                        values = struct.unpack("<7d", payload)
                        data['base_pos'] = np.array(values[:3], dtype=np.float64)
                        # MuJoCo输出(w,x,y,z)，UE可能用(x,y,z,w)，这里保持原样
                        data['base_quat'] = np.array(values[3:7], dtype=np.float64)
                        
            except zmq.Again:
                # 没有更多消息
                break
            except Exception as e:
                # 解析错误，跳过
                continue
        
        return data
    
    def recv_twist_cmd(self):
        """
        接收来自 UE 的 Twist 命令（向后兼容）
        
        Returns:
            (vx, vy, vyaw) 或 None
        """
        data = self.recv_ue_data()
        return data.get('twist')
    
    def shutdown(self):
        """关闭 ZMQ 连接"""
        try:
            self.pub.setsockopt(zmq.LINGER, 0)  # 不等待发送未完成的消息
            self.pub.close()
        except:
            pass
        if self.sub is not None:
            try:
                self.sub.setsockopt(zmq.LINGER, 0)
                self.sub.close()
            except:
                pass
        try:
            self.ctx.term()
        except:
            pass
        print("[URLabBridge] Shutdown")


def pd_control(target_q, q, kp, target_dq, dq, kd):
    """Calculates torques from position commands"""
    return (target_q - q) * kp + (target_dq - dq) * kd


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RoboMimic URLab Bridge")
    parser.add_argument("--prefix", type=str, default="g1", help="Articulation prefix in Unreal")
    parser.add_argument("--state-ep", type=str, default="tcp://127.0.0.1:5555", help="State ZMQ endpoint (UE PUB/Sensor -> Python SUB)")
    parser.add_argument("--ctrl-ep", type=str, default="tcp://127.0.0.1:5556", help="Control ZMQ endpoint (Python PUB -> UE SUB/Control)")
    parser.add_argument("--use-mujoco-sim", action="store_true", help="使用MuJoCo仿真数据替代UE传感器数据（默认使用UE数据）")
    parser.add_argument("--robot-xml", type=str, default=None, help="机器人XML路径（相对于PROJECT_ROOT），例如g1_description/scene.xml或g1_description_bridge/g1_29dof_rev_1_0_position.xml。不指定则使用mujoco.yaml中的xml_path")
    args = parser.parse_args()
    
    # 如果 state_ep 为空字符串，则禁用传感器接收
    if args.state_ep == "":
        args.state_ep = None
    # 如果 ctrl_ep 为空字符串，则禁用控制发送
    if args.ctrl_ep == "":
        args.ctrl_ep = None
    
    # 默认使用UE数据，除非指定--use-mujoco-sim
    args.use_ue_state = not args.use_mujoco_sim
    
    # 检查参数兼容性
    if args.use_ue_state and args.state_ep is None:
        print("[URLab] Warning: 需要 state-ep 连接才能使用UE数据，使用MuJoCo仿真数据替代")
        args.use_ue_state = False
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    mujoco_yaml_path = os.path.join(current_dir, "config", "mujoco.yaml")
    with open(mujoco_yaml_path, "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        simulation_dt = config["simulation_dt"]
        control_decimation = config["control_decimation"]
    
    # 根据参数决定使用哪个XML
    if args.robot_xml:
        xml_path = os.path.join(PROJECT_ROOT, args.robot_xml)
        print(f"[URLab] Using robot XML from args: {xml_path}")
    else:
        xml_path = os.path.join(PROJECT_ROOT, config["xml_path"])
        print(f"[URLab] Using robot XML from config: {xml_path}")
    
    # 加载 MuJoCo 模型用于仿真（但不显示 viewer）
    import mujoco
    m = mujoco.MjModel.from_xml_path(xml_path)
    d = mujoco.MjData(m)
    m.opt.timestep = simulation_dt
    mj_per_step_duration = simulation_dt * control_decimation
    num_joints = m.nu
    policy_output_action = np.zeros(num_joints, dtype=np.float32)
    kps = np.zeros(num_joints, dtype=np.float32)
    kds = np.zeros(num_joints, dtype=np.float32)
    sim_counter = 0
    
    state_cmd = StateAndCmd(num_joints)
    policy_output = PolicyOutput(num_joints)
    FSM_controller = FSM(state_cmd, policy_output, use_ue_config=args.use_ue_state)
    
    joystick = JoyStick()
    keyboard = Keyboard()
    
    # 初始化 URLab Bridge
    bridge = URLabBridge(prefix=args.prefix, state_ep=args.state_ep, ctrl_ep=args.ctrl_ep)
    
    # 如果使用UE数据，建立joint_name到index的映射
    joint_name_to_idx = {}
    if args.use_ue_state:
        # 从MuJoCo模型获取joint名称和对应actuator索引
        for i in range(m.njnt):
            jnt_name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, i)
            if jnt_name:
                # joint索引通常从0开始，但qpos可能有偏移
                # 这里我们假设自由joint(qpos前7个是根节点位置+四元数)
                # 实际joint从qpos[7]开始
                pass
        # 更简单的方式：使用MuJoCo的actuator名称
        for i in range(m.nu):
            act_name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i)
            if act_name:
                joint_name_to_idx[act_name] = i
        print(f"[URLab] UE mode enabled, mapped {len(joint_name_to_idx)} joints from MuJoCo")
    
    Running = True
    
    # 50Hz控制频率限制
    CONTROL_FREQ = 50.0  # Hz
    CONTROL_PERIOD = 1.0 / CONTROL_FREQ  # 0.02s = 20ms
    _last_control_send_time = 0.0
    
    # Shift+1 自动切换LOCO模式的状态跟踪
    _auto_loco_switch_time = None
    _immediate_pos_reset = False
    
    # 重复数据检测
    _last_sent_positions = None
    _same_data_count = 0
    _max_same_data_count = 3
    
    # 策略状态跟踪（仅切换时打印）
    _last_printed_policy = None
    
    # 延迟一帧的控制信号（匹配MuJoCo行为）
    _prev_policy_output_action = None
    
    print(f"[URLab] Running policy loop — Ctrl+C to stop")
    print(f"[URLab] Control frequency limited to {CONTROL_FREQ}Hz ({CONTROL_PERIOD*1000:.1f}ms)")
    
    try:
        while Running:
            step_start = time.time()
            
            try:
                if joystick.is_button_pressed(JoystickButton.SELECT):
                    Running = False

                joystick.update()
                keyboard.update()
                
                # --- 手柄控制 ---
                if joystick.is_button_released(JoystickButton.L3):
                    state_cmd.skill_cmd = FSMCommand.PASSIVE
                if joystick.is_button_released(JoystickButton.START):
                    state_cmd.skill_cmd = FSMCommand.POS_RESET
                if joystick.is_button_released(JoystickButton.A) and joystick.is_button_pressed(JoystickButton.R1):
                    state_cmd.skill_cmd = FSMCommand.LOCO
                if joystick.is_button_released(JoystickButton.X) and joystick.is_button_pressed(JoystickButton.R1):
                    state_cmd.skill_cmd = FSMCommand.SKILL_1
                if joystick.is_button_released(JoystickButton.Y) and joystick.is_button_pressed(JoystickButton.R1):
                    state_cmd.skill_cmd = FSMCommand.SKILL_2
                if joystick.is_button_released(JoystickButton.B) and joystick.is_button_pressed(JoystickButton.R1):
                    state_cmd.skill_cmd = FSMCommand.SKILL_3
                if joystick.is_button_released(JoystickButton.Y) and joystick.is_button_pressed(JoystickButton.L1):
                    state_cmd.skill_cmd = FSMCommand.SKILL_4
                
                # 手柄摇杆控制速度
                state_cmd.vel_cmd[0] = -joystick.get_axis_value(1)
                state_cmd.vel_cmd[1] = -joystick.get_axis_value(0)
                state_cmd.vel_cmd[2] = -joystick.get_axis_value(3)
                
                # --- 键盘控制 ---
                if keyboard.is_key_pressed('ESCAPE'):
                    print("[Keyboard] ESC pressed -> Exit")
                    Running = False
                if keyboard.is_key_released('P'):
                    print("[Keyboard] P released -> PASSIVE mode")
                    state_cmd.skill_cmd = FSMCommand.PASSIVE
                if keyboard.is_key_released('SPACE'):
                    print("[Keyboard] SPACE released -> POS_RESET mode")
                    state_cmd.skill_cmd = FSMCommand.POS_RESET
                # 技能切换：Shift+主键盘数字 或 直接按小键盘数字
                if keyboard.is_key_pressed('LSHIFT') or keyboard.is_key_pressed('RSHIFT'):
                    if keyboard.is_key_released('1') or keyboard.is_key_released('!'):
                        print("[Keyboard] Shift+1 released -> LOCO mode then immediate POS_RESET")
                        state_cmd.skill_cmd = FSMCommand.LOCO
                        # 设置标志，下一帧立即执行POS_RESET
                        _immediate_pos_reset = True
                        # 设置定时器，POS_RESET完成后（2秒）自动回到LOCO
                        _auto_loco_switch_time = time.time() + 2.5  # 2.5秒后自动切换LOCO
                        print(f"[URLab] Will auto-switch to LOCO at t={_auto_loco_switch_time:.1f} (after POS_RESET)")
                    if keyboard.is_key_released('2') or keyboard.is_key_released('@'):
                        print("[Keyboard] Shift+2 released -> SKILL_1 (Dance) mode")
                        state_cmd.skill_cmd = FSMCommand.SKILL_1
                    if keyboard.is_key_released('3') or keyboard.is_key_released('#'):
                        print("[Keyboard] Shift+3 released -> SKILL_2 mode")
                        state_cmd.skill_cmd = FSMCommand.SKILL_2
                    if keyboard.is_key_released('4') or keyboard.is_key_released('$'):
                        print("[Keyboard] Shift+4 released -> SKILL_3 mode")
                        state_cmd.skill_cmd = FSMCommand.SKILL_3
                    if keyboard.is_key_released('5') or keyboard.is_key_released('%'):
                        print("[Keyboard] Shift+5 released -> SKILL_4 mode")
                        state_cmd.skill_cmd = FSMCommand.SKILL_4
                # 小键盘数字 (无需Shift)
                if keyboard.is_key_released('NUMPAD1'):
                    print("[Keyboard] Numpad1 released -> LOCO mode")
                    state_cmd.skill_cmd = FSMCommand.LOCO
                if keyboard.is_key_released('NUMPAD2'):
                    print("[Keyboard] Numpad2 released -> SKILL_1 (Dance) mode")
                    state_cmd.skill_cmd = FSMCommand.SKILL_1
                if keyboard.is_key_released('NUMPAD3'):
                    print("[Keyboard] Numpad3 released -> SKILL_2 mode")
                    state_cmd.skill_cmd = FSMCommand.SKILL_2
                if keyboard.is_key_released('NUMPAD4'):
                    print("[Keyboard] Numpad4 released -> SKILL_3 mode")
                    state_cmd.skill_cmd = FSMCommand.SKILL_3
                if keyboard.is_key_released('NUMPAD5'):
                    print("[Keyboard] Numpad5 released -> SKILL_4 mode")
                    state_cmd.skill_cmd = FSMCommand.SKILL_4
                
                # Shift + WASD/QE 控制移动
                if keyboard.is_key_pressed('LSHIFT') or keyboard.is_key_pressed('RSHIFT'):
                    key_vx = keyboard.get_axis_from_keys('S', 'W')
                    key_vy = keyboard.get_axis_from_keys('A', 'D')
                    key_vyaw = keyboard.get_axis_from_keys('Q', 'E')
                else:
                    key_vx = 0.0
                    key_vy = 0.0
                    key_vyaw = 0.0
                
                # 合并键盘和手柄输入
                if key_vx != 0:
                    state_cmd.vel_cmd[0] = key_vx
                if key_vy != 0:
                    state_cmd.vel_cmd[1] = key_vy
                if key_vyaw != 0:
                    state_cmd.vel_cmd[2] = key_vyaw
                
                # 方向键也控制移动
                arrow_vx = keyboard.get_axis_from_keys('DOWN', 'UP')
                arrow_vy = keyboard.get_axis_from_keys('LEFT', 'RIGHT')
                if arrow_vx != 0:
                    state_cmd.vel_cmd[0] = arrow_vx
                if arrow_vy != 0:
                    state_cmd.vel_cmd[1] = -arrow_vy
                
                # Shift+1 自动切换LOCO模式：检查时间并自动切换
                if _auto_loco_switch_time is not None and time.time() >= _auto_loco_switch_time:
                    print(f"[URLab] Auto-switching to LOCO mode (t={time.time():.1f})")
                    state_cmd.skill_cmd = FSMCommand.LOCO
                    _auto_loco_switch_time = None  # 重置定时器
                
                # Shift+1 后立即执行POS_RESET（如果标志已设置）
                if _immediate_pos_reset:
                    print("[URLab] Immediate POS_RESET after LOCO")
                    state_cmd.skill_cmd = FSMCommand.POS_RESET
                    _immediate_pos_reset = False
                
                # 接收来自 UE 的传感器数据
                if args.use_ue_state:
                    ue_data = bridge.recv_ue_data()
                    
                    # 首次收到数据时打印状态（使用全局标志）
                    if ue_data and not globals().get('_first_ue_data_printed', False):
                        print(f"[URLab] First UE data received: {len(ue_data.get('joint_pos', {}))} joints, {len(ue_data.get('sensors', {}))} sensors")
                        if ue_data.get('sensors'):
                            print(f"[URLab] Sensors: {list(ue_data['sensors'].keys())}")
                        globals()['_first_ue_data_printed'] = True
                    
                    # 使用UE的twist命令（如果可用）
                    if ue_data.get('twist') is not None:
                        state_cmd.vel_cmd[:] = ue_data['twist']
                    
                    # 提取UE的关节位置/速度
                    if ue_data.get('joint_pos'):
                        # 调试：首次收到时检查关节名称匹配
                        if not globals().get('_first_joint_match_debug', False):
                            ue_joints = list(ue_data['joint_pos'].keys())
                            print(f"[URLab] UE joints received: {ue_joints[:5]}... (total {len(ue_joints)})")
                            print(f"[URLab] Local mapping keys: {list(joint_name_to_idx.keys())[:5]}...")
                            # 检查未匹配的关节
                            unmatched = [j for j in ue_joints if j not in joint_name_to_idx]
                            if unmatched:
                                print(f"[URLab] WARNING: Unmatched joints: {unmatched[:5]}...")
                            globals()['_first_joint_match_debug'] = True
                        
                        matched_count = 0
                        for joint_name, pos in ue_data['joint_pos'].items():
                            if joint_name in joint_name_to_idx:
                                idx = joint_name_to_idx[joint_name]
                                state_cmd.q[idx] = pos
                                matched_count += 1
                        for joint_name, vel in ue_data['joint_vel'].items():
                            if joint_name in joint_name_to_idx:
                                idx = joint_name_to_idx[joint_name]
                                state_cmd.dq[idx] = vel
                        # 调试输出
                        if not globals().get('_first_joint_match_debug', False):
                            print(f"[URLab] Matched {matched_count}/{len(ue_data['joint_pos'])} joints")
                        
                        # 首次收到有效UE数据时，用当前关节位置初始化policy_output_action
                        # 避免初始发送全0导致机器人摔倒
                        if not globals().get('_policy_output_initialized', False):
                            policy_output_action[:] = state_cmd.q.copy()
                            globals()['_policy_output_initialized'] = True
                            print(f"[URLab] Initialized policy_output_action from UE joint positions: {policy_output_action[:3].round(3)}...")
                    
                    # 提取IMU数据
                    if 'imu-torso-angular-velocity' in ue_data.get('sensors', {}):
                        state_cmd.ang_vel[:] = ue_data['sensors']['imu-torso-angular-velocity'][:3]
                    
                    # 提取base_quat (从framequat)
                    if 'torso-framequat' in ue_data.get('sensors', {}):
                        quat = ue_data['sensors']['torso-framequat']
                        # UE格式通常是(x,y,z,w)，MuJoCo使用(w,x,y,z)
                        if len(quat) == 4:
                            # 转换为MuJoCo格式 (w,x,y,z)
                            state_cmd.base_quat = np.array([quat[3], quat[0], quat[1], quat[2]])
                            state_cmd.gravity_ori = get_gravity_orientation(state_cmd.base_quat)
                            # 调试：首次收到时打印姿态
                            if not globals().get('_first_quat_printed', False):
                                print(f"[URLab] First quat received: {state_cmd.base_quat}")
                                print(f"[URLab] Gravity orientation: {state_cmd.gravity_ori}")
                                globals()['_first_quat_printed'] = True
                    else:
                        # 没有收到姿态数据时，使用默认的直立姿态
                        if not globals().get('_quat_warning_printed', False):
                            print("[URLab] Warning: No torso-framequat sensor, using default upright pose")
                            globals()['_quat_warning_printed'] = True
                        # 默认直立姿态 (w=1, x=0, y=0, z=0)
                        state_cmd.base_quat = np.array([1.0, 0.0, 0.0, 0.0])
                        state_cmd.gravity_ori = np.array([0.0, 0.0, -1.0])  # 重力向下
                else:
                    # 接收来自 UE 的 twist 命令（可选，覆盖本地输入）
                    ue_twist = bridge.recv_twist_cmd()
                    if ue_twist is not None:
                        state_cmd.vel_cmd[:] = ue_twist
                
                # MuJoCo 仿真步进（仅在非UE模式下使用，UE模式下仅用于策略输出计算）
                if not args.use_ue_state:
                    tau = pd_control(policy_output_action, d.qpos[7:], kps, np.zeros_like(kps), d.qvel[6:], kds)
                    d.ctrl[:] = tau
                    mujoco.mj_step(m, d)
                sim_counter += 1
                
                # 每帧都运行策略并发送控制（不移除control_decimation以维持策略频率）
                if sim_counter % control_decimation == 0:
                    if not args.use_ue_state:
                        # MuJoCo模式：从仿真获取数据
                        qj = d.qpos[7:]
                        dqj = d.qvel[6:]
                        quat = d.qpos[3:7]
                        omega = d.qvel[3:6] 
                        gravity_orientation = get_gravity_orientation(quat)
                        
                        state_cmd.q = qj.copy()
                        state_cmd.dq = dqj.copy()
                        state_cmd.gravity_ori = gravity_orientation.copy()
                        state_cmd.base_quat = quat.copy()
                        state_cmd.ang_vel = omega.copy()
                    
                    # UE模式：先发送上一帧的控制信号（匹配MuJoCo的1帧延迟）
                    if args.use_ue_state:
                        if _prev_policy_output_action is not None:
                            kps = policy_output.kps.copy()
                            kds = policy_output.kds.copy()
                            # 打印当前策略状态（仅在切换时打印）
                            if FSM_controller.cur_policy:
                                state_name = getattr(FSM_controller.cur_policy, 'name_str', str(FSM_controller.cur_policy))
                                if state_name != _last_printed_policy:
                                    print(f"[URLab] Policy switched to: {state_name}")
                                    _last_printed_policy = state_name
                        else:
                            # 第一帧，初始化控制信号
                            _prev_policy_output_action = policy_output.actions.copy()
                    
                    # 运行FSM更新下一帧控制信号
                    FSM_controller.run()
                    policy_output_action = policy_output.actions.copy()
                    
                    # MuJoCo模式：打印策略状态
                    if not args.use_ue_state:
                        if FSM_controller.cur_policy:
                            state_name = getattr(FSM_controller.cur_policy, 'name_str', str(FSM_controller.cur_policy))
                            if state_name != _last_printed_policy:
                                print(f"[URLab] Policy switched to: {state_name}")
                                _last_printed_policy = state_name
                    
                    # 调试输出：查看POS_RESET模式下的控制值（每10帧打印一次）
                    current_policy = FSM_controller.cur_policy
                    if current_policy and hasattr(current_policy, 'name_str') and current_policy.name_str == "fixed_pose":
                        _debug_pos_reset_counter = globals().get('_debug_pos_reset_counter', 0)
                        if _debug_pos_reset_counter % 10 == 0:  # 每10帧打印一次
                            print(f"[DEBUG FixedPose] step={current_policy.cur_step}/{current_policy.num_step}, alpha={current_policy.alpha:.3f}")
                            print(f"[DEBUG FixedPose] init_pos[0:6]={current_policy.init_dof_pos[0:6].round(3)}")
                            print(f"[DEBUG FixedPose] target[0:6]={current_policy.default_angles[0:6].round(3)}")
                            print(f"[DEBUG FixedPose] output[0:6]={policy_output_action[0:6].round(3)}")
                            print(f"[DEBUG FixedPose] kps[0:6]={current_policy.kps[0:6].round(1)}, kds[0:6]={current_policy.kds[0:6].round(1)}")
                        globals()['_debug_pos_reset_counter'] = _debug_pos_reset_counter + 1
                    
                    # MuJoCo模式：更新kps/kds
                    if not args.use_ue_state:
                        kps = policy_output.kps.copy()
                        kds = policy_output.kds.copy()
                    
                    # UE模式下发送PD增益（每个策略可能有不同增益）
                    # 注意：UE使用position执行器时，PD增益由XML内部定义，不需要发送
                    # if args.use_ue_state:
                    #     # 检查增益是否变化，如果变化则重新发送
                    #     last_kps = globals().get('_last_kps')
                    #     last_kds = globals().get('_last_kds')
                    #     need_send = False
                    #     if last_kps is None or last_kds is None:
                    #         need_send = True
                    #     else:
                    #         if not np.allclose(kps, last_kps) or not np.allclose(kds, last_kds):
                    #             need_send = True
                    #     if need_send:
                    #         bridge.send_gains(kps, kds)
                    #         globals()['_last_kps'] = kps.copy()
                    #         globals()['_last_kds'] = kds.copy()
                    
                    # 发送关节状态到 Unreal Engine（50Hz频率限制 + 重复数据检测）
                    current_time = time.time()
                    if current_time - _last_control_send_time >= CONTROL_PERIOD:
                        # 检查数据是否重复
                        positions_to_send = _prev_policy_output_action if args.use_ue_state else qj
                        if _last_sent_positions is not None and np.allclose(positions_to_send, _last_sent_positions, atol=1e-6):
                            _same_data_count += 1
                            if _same_data_count >= _max_same_data_count:
                                # 数据重复超过3次，跳过发送
                                if _same_data_count == _max_same_data_count:
                                    print(f"[URLabBridge] Data unchanged for {_same_data_count} times, skipping send...")
                                _last_control_send_time = current_time
                            else:
                                # 重复次数未超过阈值，正常发送
                                if args.use_ue_state:
                                    if globals().get('_policy_output_initialized', False):
                                        bridge.send_joint_states(_prev_policy_output_action)
                                else:
                                    bridge.send_joint_states(qj, dqj)
                                _last_control_send_time = current_time
                                _last_sent_positions = positions_to_send.copy()
                        else:
                            # 数据变化，重置计数并发送
                            if _same_data_count >= _max_same_data_count:
                                print(f"[URLabBridge] Data changed, resuming send")
                            _same_data_count = 0
                            if args.use_ue_state:
                                if globals().get('_policy_output_initialized', False):
                                    bridge.send_joint_states(_prev_policy_output_action)
                            else:
                                bridge.send_joint_states(qj, dqj)
                            _last_control_send_time = current_time
                            _last_sent_positions = positions_to_send.copy()
                            # UE模式：保存当前控制信号供下一帧使用（1帧延迟）
                            if args.use_ue_state:
                                _prev_policy_output_action = policy_output_action.copy()
                    
            except Exception as e:
                import traceback
                print(f"[URLab] Error in loop: {e}")
                traceback.print_exc()
                
    except KeyboardInterrupt:
        print("[URLab] Stopping...")
    finally:
        keyboard.stop()
        bridge.shutdown()
        # 清理全局标志
        for key in ['_first_ue_data_printed', '_policy_output_initialized', '_last_kps', '_last_kds', 
                    '_first_printed_joint_count', '_first_printed_sensor_count', '_last_prefix', 
                    '_frame_count', '_send_count', '_last_print_time', '_last_print_count',
                    '_quat_warning_printed', '_first_quat_printed', 
                    '_auto_loco_switch_time', '_immediate_pos_reset',
                    '_last_sent_positions', '_same_data_count', '_last_printed_policy',
                    '_debug_pos_reset_counter', '_prev_policy_output_action']:
            if key in globals():
                del globals()[key]
        print("[URLab] Done")

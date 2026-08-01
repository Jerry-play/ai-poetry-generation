# thermal_printer.py
"""
USB 热敏打印机控制模块 (ESC/POS 协议)
适用环境: Windows + USB连接 + 58mm纸张 + 无切刀机型
依赖安装: pip install python-escpos pyusb Pillow
注意: 本代码采用底层指令兼容模式，适配 python-escpos 3.0 - 4.0+
"""

import logging
import os
from typing import Union
from escpos.printer import Usb
from usb.core import USBError
from PIL import Image

__all__ = ["ThermalPrinter"]
logger = logging.getLogger(__name__)


class ThermalPrinter:
    """USB 热敏打印机控制类（自动适配 58mm 纸宽，支持灰度抖动优化）"""

    # 58mm 热敏纸有效打印区域约 384 像素 (基于 203 DPI)
    MAX_WIDTH_58MM = 384

    def __init__(self, vid: int, pid: int, timeout: float = 5.0, encoding: str = "gbk"):
        self.vid = vid
        self.pid = pid
        self.timeout_ms = int(timeout * 1000)
        self.encoding = encoding
        self._printer: Usb = None
        self._connect()

    def _connect(self) -> None:
        try:
            # 尝试初始化，兼容不同版本的参数
            try:
                self._printer = Usb(self.vid, self.pid, timeout=self.timeout_ms, encoding=self.encoding)
            except TypeError:
                self._printer = Usb(self.vid, self.pid, timeout=self.timeout_ms)

            # 强制修正 timeout 为整数，修复 libusb1 类型错误
            if hasattr(self._printer, 'timeout'):
                self._printer.timeout = self.timeout_ms

            logger.info(f"✅ 打印机已连接 (VID:{hex(self.vid)} PID:{hex(self.pid)})")
        except USBError as e:
            logger.error(f"❌ USB 连接失败: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 初始化异常: {e}")
            raise

    def _raw(self, data: bytes):
        """安全发送原始指令"""
        if hasattr(self._printer, '_raw'):
            self._printer._raw(data)
        elif hasattr(self._printer, 'device') and hasattr(self._printer, 'out_ep'):
            # 极端情况：直接通过 usb 设备写入
            self._printer.device.write(self._printer.out_ep, data, self._printer.timeout)
        else:
            raise AttributeError("无法找到发送原始指令的方法")

    def set_style(self, align: str = "left", bold: bool = False,
                  double_height: bool = False, double_width: bool = False) -> None:
        """设置文本样式 (使用底层指令以确保兼容)"""
        # ESC ! n 指令
        # Bit 0-1: Character font (00: Font A, 01: Font B)
        # Bit 2: Bold (1: on)
        # Bit 3: Double height (1: on)
        # Bit 4: Double width (1: on)
        # Bit 5: Underline (1: on)

        mode = 0
        if bold: mode |= 0x08  # 注意：不同打印机位定义可能不同，这里用通用标准
        if double_height: mode |= 0x10
        if double_width: mode |= 0x20

        # 更通用的加粗/宽高设置指令: ESC E n (bold), GS ! n (size)
        # 为了简单且兼容，我们尽量使用 python-escpos 的 set，如果失败则忽略
        try:
            align_map = {"left": 0, "center": 1, "right": 2}
            align_val = align_map.get(align.lower(), 0)

            # 尝试调用库方法
            if hasattr(self._printer, 'set'):
                self._printer.set(align=align.lower(), bold=bold, double_height=double_height,
                                  double_width=double_width)
            else:
                # 手动发送对齐指令 ESC a n
                self._raw(bytes([0x1B, 0x61, align_val]))
                # 手动发送加粗指令 ESC E n
                self._raw(bytes([0x1B, 0x45, 1 if bold else 0]))
                # 手动发送宽高指令 GS ! n
                size_val = 0
                if double_height: size_val |= 0x10
                if double_width: size_val |= 0x01
                self._raw(bytes([0x1D, 0x21, size_val]))
        except Exception as e:
            logger.warning(f"⚠️ 设置样式失败: {e}")

    def print_text(self, text: str) -> None:
        """打印文本"""
        if not text.endswith("\n"):
            text += "\n"

        # 编码处理
        if hasattr(self._printer, 'encoding') and self._printer.encoding:
            encoded_text = text.encode(self._printer.encoding, errors='ignore')
        else:
            encoded_text = text.encode(self.encoding, errors='ignore')

        # 发送文本
        if hasattr(self._printer, 'text'):
            try:
                # 尝试库方法，不带 encoding 参数
                self._printer.text(text)
            except TypeError:
                # 如果库方法仍报错，直接写原始数据
                self._raw(encoded_text)
        else:
            self._raw(encoded_text)

    def print_txt_file(self, file_path: str, align: str = "left", bold: bool = False,
                       double_height: bool = False, double_width: bool = False) -> None:
        """
        打印.txt文件内容
        
        Args:
            file_path: txt文件路径
            align: 对齐方式 (left/center/right)
            bold: 是否加粗
            double_height: 是否双倍高度
            double_width: 是否双倍宽度
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            # 检测文件编码并读取内容
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            content = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    logger.info(f"📄 使用 {encoding} 编码读取文件成功")
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                raise ValueError(f"无法解码文件: {file_path}")
            
            # 设置样式
            self.set_style(align=align, bold=bold, 
                          double_height=double_height, double_width=double_width)
            
            # 逐行打印，保持格式
            lines = content.split('\n')
            for line in lines:
                # 处理空行
                if line.strip() == '':
                    self.feed(1)
                else:
                    self.print_text(line)
            
            logger.info(f"✅ 文件打印完成: {os.path.basename(file_path)}")
            
        except Exception as e:
            logger.error(f"❌ 打印txt文件失败: {e}")
            raise

    def print_line(self, length: int = 32, char: str = "-") -> None:
        """打印分隔线"""
        self.print_text(char * length)

    def print_image(self, source: Union[str, Image.Image],
                    max_width: int = MAX_WIDTH_58MM, dither: bool = True) -> None:
        """
        智能图片打印：自适应缩放 + 灰度转换 + 二值抖动
        """
        try:
            # 1. 加载图片
            if isinstance(source, str):
                if not os.path.exists(source):
                    raise FileNotFoundError(f"图片不存在: {source}")
                img = Image.open(source)
            else:
                img = source.copy()

            # 2. 等比缩放至安全宽度 (严格整数化)
            w, h = img.size
            if w > max_width:
                ratio = float(max_width) / float(w)
                new_w = int(max_width)
                new_h = int(round(h * ratio))
                new_h = max(1, new_h)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # 再次确认尺寸是整数
            w, h = img.size
            if w != int(w) or h != int(h):
                img = img.resize((int(w), int(h)), Image.Resampling.NEAREST)

            # 3. 灰度化 + 二值抖动处理
            img = img.convert("L")
            if dither:
                img = img.convert("1", dither=Image.FLOYDSTEINBERG)
            else:
                img = img.convert("1")

            # 4. 发送打印
            if hasattr(self._printer, 'image'):
                self._printer.image(img, impl="bitImageColumn")
            else:
                raise AttributeError("打印机对象不支持 image 方法")

            logger.info(f"🖼️ 图片已发送 (尺寸:{img.size[0]}x{img.size[1]})")

        except Exception as e:
            logger.error(f"❌ 图片处理/打印失败: {e}")
            raise

    def feed(self, lines: int = 1) -> None:
        """走纸 (使用原始指令 ESC d n，确保 100% 兼容)"""
        # ESC d n: Print and feed n lines
        cmd = bytes([0x1B, 0x64, lines])
        self._raw(cmd)

    def reset(self) -> None:
        """恢复默认样式 (ESC @)"""
        self._raw(bytes([0x1B, 0x40]))

    def close(self) -> None:
        """释放资源"""
        if self._printer:
            try:
                self._printer.close()
                logger.info("🔌 打印机连接已释放")
            except Exception as e:
                logger.warning(f"⚠️ 释放连接异常: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ================= 独立测试入口 =================
if __name__ == "__main__":
    # 🔹 替换为你的打印机 VID/PID
    USB_VID = 0x09C5
    USB_PID = 0x58DE

    # # 🔹 替换为你的测试图片路径
    # TEST_IMG = "img.png"
    #
    # try:
    #     with ThermalPrinter(vid=USB_VID, pid=USB_PID, encoding='gbk') as p:
    #         p.set_style(align="center", bold=False)
    #         p.print_text("📦 模块测试打印")
    #
    #         p.reset()
    #         p.print_line()
    #
    #         if os.path.exists(TEST_IMG):
    #             p.print_image(TEST_IMG, dither=True)
    #         else:
    #             p.print_text(f"[未找到图片: {TEST_IMG}]")
    #
    #         p.feed(2)
    #         p.set_style(align="center")
    #         p.print_text("请沿虚线撕取")
    #         p.print_line(char=".")
    #         p.feed(2)
    #
    # except Exception as e:
    #     logger.error(f"测试失败: {e}")
    #     import traceback
    #     traceback.print_exc()

    with ThermalPrinter(vid=USB_VID, pid=USB_PID, encoding='gbk') as p:
        p.set_style(align="left", bold=False)
        p.print_txt_file(r'D:/a.txt')
        p.feed(2)

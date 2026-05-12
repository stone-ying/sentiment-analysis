# -*- coding: utf-8 -*-
"""
词云生成模块
根据关键词频率生成词云图片
"""

import os
import io
import base64
from typing import List, Tuple

try:
    from wordcloud import WordCloud
    HAS_WORDCLOUD = True
except ImportError:
    HAS_WORDCLOUD = False

try:
    import matplotlib
    matplotlib.use('Agg')  # 无头模式
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class WordCloudGenerator:
    """词云生成器"""

    def __init__(self, font_path: str = None, width: int = 800, height: int = 400):
        self.width = width
        self.height = height
        self.font_path = font_path or self._find_chinese_font()

    def _find_chinese_font(self) -> str:
        """查找系统中可用的中文字体"""
        # Windows 中文字体路径
        windows_fonts = [
            "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
            "C:/Windows/Fonts/simhei.ttf",     # 黑体
            "C:/Windows/Fonts/simsun.ttc",     # 宋体
            "C:/Windows/Fonts/simkai.ttf",     # 楷体
        ]
        
        for font in windows_fonts:
            if os.path.exists(font):
                return font
        
        return None  # 使用默认字体

    def generate(self, keywords: List[Tuple[str, int]], output_path: str = None) -> str:
        """
        生成词云图片
        
        Args:
            keywords: [(关键词, 频次), ...]
            output_path: 输出文件路径，为None则返回base64编码
        
        Returns:
            输出文件路径或base64编码的图片
        """
        if not HAS_WORDCLOUD:
            return self._generate_fallback(keywords, output_path)

        # 构建词频字典
        freq_dict = {word: count for word, count in keywords}
        
        # 创建词云
        wc_params = {
            "width": self.width,
            "height": self.height,
            "background_color": "white",
            "max_words": 50,
            "max_font_size": 80,
            "collocations": False,
        }
        
        if self.font_path:
            wc_params["font_path"] = self.font_path
        
        wc = WordCloud(**wc_params)
        wc.generate_from_frequencies(freq_dict)

        if output_path:
            wc.to_file(output_path)
            return output_path
        else:
            # 返回base64编码
            img_buffer = io.BytesIO()
            wc.to_image().save(img_buffer, format='PNG')
            img_buffer.seek(0)
            return base64.b64encode(img_buffer.read()).decode('utf-8')

    def generate_sentiment_chart(self, sentiment_result, output_path: str = None) -> str:
        """
        生成情绪分布饼图
        
        Args:
            sentiment_result: SentimentResult 对象
            output_path: 输出文件路径
        """
        if not HAS_MATPLOTLIB:
            return ""

        # 创建饼图
        fig, ax = plt.subplots(figsize=(6, 4))
        
        labels = ['正面', '负面', '中性']
        sizes = [
            sentiment_result.positive_ratio * 100,
            sentiment_result.negative_ratio * 100,
            sentiment_result.neutral_ratio * 100,
        ]
        colors = ['#4CAF50', '#F44336', '#FFC107']
        
        # 过滤掉0值
        non_zero = [(l, s, c) for l, s, c in zip(labels, sizes, colors) if s > 0]
        if non_zero:
            labels, sizes, colors = zip(*non_zero)
        
        ax.pie(
            sizes, labels=labels, colors=colors,
            autopct='%1.1f%%', startangle=90,
            textprops={'fontsize': 12}
        )
        ax.set_title('情绪分布', fontsize=14, fontweight='bold')

        # 设置中文字体
        if self.font_path:
            from matplotlib.font_manager import FontProperties
            font_prop = FontProperties(fname=self.font_path)
            for text in ax.texts:
                text.set_fontproperties(font_prop)
            ax.title.set_fontproperties(font_prop)

        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
            return output_path
        else:
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
            img_buffer.seek(0)
            return base64.b64encode(img_buffer.read()).decode('utf-8')

    def _generate_fallback(self, keywords: List[Tuple[str, int]], output_path: str = None) -> str:
        """降级方案：生成文本版关键词列表"""
        lines = ["📊 关键词频率统计\n"]
        max_count = keywords[0][1] if keywords else 1
        
        for word, count in keywords[:20]:
            bar_len = int(count / max_count * 20)
            bar = "█" * bar_len
            lines.append(f"  {word:6s} {bar} ({count})")
        
        text = "\n".join(lines)
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text)
            return output_path
        else:
            return text

# plugins/DigitalBomb/main.py

import os
import random
import tomllib
from loguru import logger

from WechatAPI import WechatAPIClient
from utils.decorators import on_text_message
from utils.plugin_base import PluginBase

class DigitalBomb(PluginBase):
    description = "一个简单的数字炸弹小游戏"
    author = "memor221"
    version = "1.0.0"

    def __init__(self):
        super().__init__()
        # 初始化游戏状态存储
        self.game_states = {}
        
        # 加载配置文件
        config_path = os.path.join(os.path.dirname(__file__), "config.toml")
        try:
            with open(config_path, "rb") as f:
                config = tomllib.load(f)
            
            # 读取配置
            basic_config = config.get("basic", {})
            self.enable = basic_config.get("enable", False)

            cmd_config = config.get("commands", {})
            self.commands = {
                "main": cmd_config.get("main", "数字炸弹"),
                "signup": cmd_config.get("signup", "报名"),
                "start": cmd_config.get("start", "开始游戏"),
                "end": cmd_config.get("end", "结束游戏"),
            }

            game_settings_config = config.get("game_settings", {})
            self.settings = {
                "min_players": game_settings_config.get("min_players", 2),
                "min_range": game_settings_config.get("min_range", 1),
                "max_range": game_settings_config.get("max_range", 100),
            }
            logger.info("数字炸弹插件加载成功。")

        except Exception as e:
            logger.error(f"加载数字炸弹插件配置文件失败: {e}")
            self.enable = False

    @on_text_message(priority=50)
    async def handle_game_logic(self, bot: WechatAPIClient, message: dict):
        """统一处理所有游戏相关的文本消息"""
        if not self.enable:
            return True

        content = message.get("Content", "").strip()
        if "@chatroom" not in message.get("FromWxid", ""):
            return True
            
        group_id = message["FromWxid"]
        # 注意：这里的user_id就是SenderWxid
        user_id = message.get("SenderWxid")
        
        # 增加一个保护，如果SenderWxid不存在则不处理
        if not user_id:
            logger.warning("DigitalBomb: 消息中缺少SenderWxid，无法处理。")
            return True

        parts = content.split()
        if not parts:
            return True

        if parts[0] == self.commands["main"]:
            if len(parts) > 1:
                sub_cmd = parts[1]
                if sub_cmd == self.commands["signup"]:
                    # 【代码修改】将完整的message对象传递给signup函数
                    await self.handle_signup(bot, group_id, user_id, message)
                elif sub_cmd == self.commands["start"]:
                    await self.handle_start_game(bot, group_id)
                elif sub_cmd == self.commands["end"]:
                    await self.handle_end_game(bot, group_id)
            return False

        game = self.game_states.get(group_id)
        if game and game.get('is_active', False) and content.isdigit():
            await self.handle_guess(bot, group_id, user_id, content)
            return False
        
        return True

    def _get_or_create_game(self, group_id):
        """获取或创建游戏状态"""
        if group_id not in self.game_states:
            self.game_states[group_id] = {
                'is_active': False,
                'players': [],
                'player_order': [],
                'current_turn_index': 0,
                'bomb_number': 0,
                'min_range': self.settings["min_range"],
                'max_range': self.settings["max_range"],
            }
        return self.game_states[group_id]

    def _reset_game(self, group_id):
        """重置指定群组的游戏状态"""
        if group_id in self.game_states:
            del self.game_states[group_id]
        logger.info(f"[数字炸弹] 群 {group_id} 的游戏已重置。")

    # 【代码修改】增加message参数以获取所需信息
    async def handle_signup(self, bot: WechatAPIClient, group_id: str, user_id: str, message: dict):
        """处理玩家报名"""
        game = self._get_or_create_game(group_id)

        if game.get('is_active'):
            await bot.send_text_message(group_id, "游戏已经开始，无法报名！")
            return

        # --- 【最终正确的代码修复】 ---
        # 根据您的指示和日志分析，直接从 message 字典中获取昵称，不再进行API调用
        # 优先级: DisplayName > ActualNickName > NickName > SenderWxid
        nickname = (
            message.get("DisplayName")
            or message.get("ActualNickName")
            or message.get("NickName")
            or user_id  # 使用 user_id (即SenderWxid) 作为最终备用
        )
        logger.debug(f"DigitalBomb: 为用户 {user_id} 确定的昵称为: {nickname}")
        # --- 【修复结束】 ---
        
        if any(p['user_id'] == user_id for p in game['players']):
            reply_text = f"{nickname} 您已经报过名了！"
            await bot.send_at_message(group_id, reply_text, [user_id])
            return

        game['players'].append({'user_id': user_id, 'nickname': nickname})
        start_command_hint = f"{self.commands['main']} {self.commands['start']}"
        reply_text = (
            f"{nickname} 报名成功！\n"
            f"当前报名人数：{len(game['players'])} 人\n"
            f"发送「{start_command_hint}」即可开始！"
        )
        await bot.send_at_message(group_id, reply_text, [user_id])

    async def handle_start_game(self, bot: WechatAPIClient, group_id: str):
        """处理开始游戏指令"""
        game = self.game_states.get(group_id)

        if not game or not game['players']:
            await bot.send_text_message(group_id, "还没有人报名，无法开始游戏。")
            return
        
        if game.get('is_active'):
            await bot.send_text_message(group_id, "游戏已经开始了！")
            return

        if len(game['players']) < self.settings["min_players"]:
            await bot.send_text_message(group_id, f"人数不足 {self.settings['min_players']} 人，无法开始游戏！")
            return

        game['is_active'] = True
        game['bomb_number'] = random.randint(game['min_range'], game['max_range'])
        game['player_order'] = random.sample(game['players'], len(game['players']))
        game['current_turn_index'] = 0
        
        logger.info(f"[数字炸弹] 群 {group_id} 游戏开始, 炸弹是 {game['bomb_number']}")

        player_names = " -> ".join([p['nickname'] for p in game['player_order']])
        first_player = game['player_order'][0]
        start_message = (
            f"💣 数字炸弹游戏开始！💣\n"
            f"--------------------\n"
            f"玩家顺序: {player_names}\n"
            f"数字范围: {game['min_range']} - {game['max_range']}\n"
            f"--------------------\n"
            f"请 {first_player['nickname']} 开始猜数字！"
        )
        await bot.send_at_message(group_id, start_message, [first_player['user_id']])

    async def handle_end_game(self, bot: WechatAPIClient, group_id: str):
        """处理结束游戏指令"""
        if group_id in self.game_states:
            self._reset_game(group_id)
            await bot.send_text_message(group_id, "本局游戏已由玩家手动结束。")

    async def handle_guess(self, bot: WechatAPIClient, group_id: str, user_id: str, number_str: str):
        """处理玩家的数字猜测"""
        game = self.game_states.get(group_id)
        if not game or not game.get('is_active'):
            return

        current_player = game['player_order'][game['current_turn_index']]
        if current_player['user_id'] != user_id:
            return

        try:
            guess = int(number_str)
        except ValueError:
            return

        if not (game['min_range'] <= guess <= game['max_range']):
            await bot.send_at_message(
                group_id,
                f"{current_player['nickname']}，数字必须在 {game['min_range']} 和 {game['max_range']} 之间！",
                [user_id]
            )
            return

        if guess == game['bomb_number']:
            result_text = (
                f"BOOM! 💥 炸弹是 {game['bomb_number']}！\n"
                f"--------------------\n"
                f"踩雷玩家: {current_player['nickname']}\n"
                f"--------------------\n"
                f"游戏结束！"
            )
            await bot.send_at_message(group_id, result_text, [current_player['user_id']])
            self._reset_game(group_id)
        else:
            if guess < game['bomb_number']:
                game['min_range'] = guess + 1
            else:
                game['max_range'] = guess - 1
            
            game['current_turn_index'] = (game['current_turn_index'] + 1) % len(game['player_order'])
            next_player = game['player_order'][game['current_turn_index']]
            
            reply_text = (
                f"{current_player['nickname']} 猜测 {guess}。\n"
                f"新的数字范围是：{game['min_range']} - {game['max_range']}\n"
                f"--------------------\n"
                f"请 {next_player['nickname']} 猜下一个数字！"
            )
            await bot.send_at_message(group_id, reply_text, [next_player['user_id']])
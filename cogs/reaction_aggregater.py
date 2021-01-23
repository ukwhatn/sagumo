# !/usr/bin/env python3
# -*- coding: utf-8 -*-


import asyncio
import typing
from datetime import datetime

import discord
from discord.ext import commands, tasks

from .utils.reaction_aggregation_manager import AggregationManager
from .utils.setting_manager import SettingManager

# https://starnak.hatenablog.com/entry/2018/07/28/230500
# has_roleだと動的にできないから、デコレータじゃなくてそういう関数を書く必要がある
# guild_idとroles渡して管理or利用か？を確認する


def has_some_role():
    async def predicate(ctx):
        if len(ctx.author.roles) > 1:
            return True
    return commands.check(predicate)


class reaction(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.setting_mng = SettingManager()
        self.aggregation_mng = AggregationManager()

        if not self.bot.loop.is_running():
            self.reaction_reminder.start()

    @staticmethod
    async def autodel_msg(msg: discord.Message, second: int = 5):
        """渡されたメッセージを指定秒数後に削除する関数

        Args:
            msg (discord.Message): 削除するメッセージオブジェクト
            second (int, optional): 秒数. Defaults to 5.
        """
        try:
            await msg.delete(delay=second)
        except discord.Forbidden:
            pass

    async def is_bot_user(self, guild: discord.Guild, command_user: discord.Member) -> bool:
        """そのサーバーのBOT_user役職を持っているか判定する関数

        Args:
            guild (discord.Guild): サーバーのギルドオブジェクト
            command_user (discord.Member): コマンド使用者のメンバーオブジェクト

        Returns:
            bool: 入ってたらTrue、入ってなかったらFalse

        Memo:
            管理者は使用者の権限も持つことにする
        """
        guild_DB = await self.setting_mng.get_guild(guild.id)
        bot_user_role = guild.get_role(guild_DB.bot_user_id)
        bot_manager_role = guild.get_role(guild_DB.bot_manager_id)

        if any([role in command_user.roles for role in [
               bot_manager_role, bot_user_role]]):
            return True
        else:
            return False

    async def is_bot_manager(self, guild: discord.Guild, command_user: discord.Member) -> bool:
        """そのサーバーのBOT_manager役職を持っているか判定する関数

        Args:
            guild (discord.Guild): サーバーのギルドオブジェクト
            command_user (discord.Member): コマンド使用者のメンバーオブジェクト

        Returns:
            bool: 入ってたらTrue、入ってなかったらFalse
        """
        guild_DB = await self.setting_mng.get_guild(guild.id)
        bot_manager_role = guild.get_role(guild_DB.bot_manager_id)
        if bot_manager_role in command_user.roles:
            return True
        else:
            return False

    @commands.Cog.listener()
    async def on_ready(self):
        """on_ready時に発火する関数
        """
        await self.aggregation_mng.create_table()
        await self.setting_mng.create_table()

    async def judge_and_notice(self, msg_id):
        if self.reaction_dict[msg_id]["cnt"] <= self.reaction_dict[msg_id][
                "reaction_sum"] and self.reaction_dict[msg_id]["matte"] == 0:
            channel = self.bot.get_channel(
                self.reaction_dict[msg_id]["channel"])
            mention = self.reaction_dict[msg_id]["author"]
            url = self.reaction_dict[msg_id]["url"]
            roles = self.reaction_dict[msg_id]["role"]
            roles = [channel.guild.get_role(i).name for i in roles]
            roles = ' '.join(roles)

            if len(roles) == 0:
                roles = 'None'
            else:
                roles = ' '.join(roles)

            embed = discord.Embed(title="規定数のリアクションがたまりました")
            embed.add_field(name="終了した集計のリンク", value=f"{url}", inline=False)
            embed.set_footer(text=f"対象の役職 : {roles}")

            await channel.send(f"{mention}")
            await channel.send(embed=embed)

            self.reaction_dict.pop(msg_id, None)
            # self.dump_json(self.reaction_dict)
        else:
            # self.dump_json(self.reaction_dict)
            pass

    @commands.command(aliases=['s_init'])
    async def sagumo_initialization(self, ctx, bot_manager: discord.Role, bot_user: discord.Role):
        """ギルドごとの管理者、使用者役職を登録するコマンド

        Args:
            ctx (): いつもの
            bot_manager (discord.Role): bot管理者役職
            bot_user (discord.Role): bot使用者役職
        """
        if await self.setting_mng.is_exist(ctx.guild.id):
            await self.setting_mng.update_guild(
                guild_id=ctx.guild.id,
                bot_manager_id=bot_manager.id,
                bot_user_id=bot_user.id)
            await ctx.send(f'{ctx.guild}のbot管理者に{bot_manager.mention}を、bot操作者に{bot_user.mention}に更新しました')
        else:
            await self.setting_mng.register_guild(
                guild_id=ctx.guild.id,
                bot_manager_id=bot_manager.id,
                bot_user_id=bot_user.id)
            await ctx.send(f'{ctx.guild}のbot管理者に{bot_manager.mention}を、bot操作者に{bot_user.mention}を設定しました')

    @commands.command(aliases=['cnt'])
    @has_some_role()
        """リアクション集計を行うbot

        Args:
            ctx (discord.ext.commands.context.Context): いつもの
            target_value (int, optional): リアクションの合計数. Defaults to 0.

        Raises:
            commands.CheckFailure: 権限を持っていなかったらCheckFailureを上げるようにした、on_errorで拾う
        """
        if not await self.is_bot_user(ctx.guild, ctx.author):
            raise commands.CheckFailure
            await ctx.send("引数を正しく入力してください")
            return

        today = datetime.today()
        now = today.strftime('%Y-%m-%d %H:%M:%S')

        if len(roles) == 0:
            insert_roles = []
        else:
            insert_roles = [i.id for i in roles]
        #  (id , guild, channel , cnt  , reaction_sum, matte, author , timestamp , role )

        # 書き込み処理

        first_msg = f"{ctx.author.mention}\nリアクション集計を行います: 目標リアクション数 : **{num}**"

        if len(roles) > 0:
            mid_msg = f"指定された役職 : {' '.join([i.name for i in roles])}\n"
        else:
            mid_msg = ""

        last_msg = "本メッセージにリアクションをつけてください"

        await ctx.send(f"{first_msg}\n{mid_msg}{last_msg}")

    @ count.error
    async def count_error(self, ctx, error):
        print(error)
        if isinstance(error, commands.BadArgument):
            notify_msg = await ctx.send(f'{ctx.author.mention}\n引数エラーです\n順番が間違っていませんか？')
            await self.autodel_msg(notify_msg)
        else:
            raise ValueError

    @ commands.command(aliases=['lsre'])
    @ has_some_role()
    async def list_reaction(self, ctx):
        if len(self.reaction_dict) == 0:
            await ctx.send("集計中のリアクションはありません")
        else:
            embed = discord.Embed(
                title="集計中のリアクションは以下の通りです",
                description=f"{len(self.reaction_dict)}件集計中",
                color=0xffffff)

            for num, i in enumerate(self.reaction_dict):
                auth = self.reaction_dict[i]["author"]
                time = self.reaction_dict[i]["time"]
                url = self.reaction_dict[i]["url"]
                role = ' '.join(
                    [f'<@&{i}>' for i in self.reaction_dict[i]["role"]])
                reaction_sum = self.reaction_dict[i]["reaction_sum"]
                reaction_cnt = self.reaction_dict[i]["cnt"]

                if self.reaction_dict[i]["matte"] > 0:
                    matte = " **待って！**"
                else:
                    matte = ""

                embed.add_field(
                    name=f"{num+1}番目",
                    value=f"ID : {i} by : {auth} time : {time} progress : {reaction_sum}/{reaction_cnt}{matte} role : {role}\n{url}",
                    inline=False)
            embed.set_footer(text="あんまり貯めないでね")
            await ctx.send(embed=embed)

    @ commands.command()
    @ commands.is_owner()
    async def clear_all(self, ctx):
        self.reaction_dict = {}
        # self.dump_json(self.reaction_dict)
        await ctx.send("全てのデータを削除しました")

    @ commands.command(aliases=['rm'])
    @ commands.has_permissions(ban_members=True)
    async def remove(self, ctx, num: typing.Optional[str]):
        try:
            aggregate_id = num.replace(" ", "")
            url = self.reaction_dict[aggregate_id]["url"]
            del self.reaction_dict[aggregate_id]
            # self.dump_json(self.reaction_dict)
            await ctx.send(f"1件削除しました\n{url}")
        except KeyError:
            await ctx.send("キーが存在しません")

    @ commands.Cog.listener()
    async def on_raw_reaction_add(self, reaction):
        # await
        for msg_id in list(self.reaction_dict):
            if int(msg_id) == reaction.message_id:
                channel = self.bot.get_channel(reaction.channel_id)
                member_role_ids = [role.id for role in reaction.member.roles]
                reaction_role_ids = self.reaction_dict[msg_id]["role"]

                if len(reaction_role_ids) == 0:
                    pass
                else:
                    if len(set(reaction_role_ids) & set(member_role_ids)) == 0:
                        self.reaction_dict[msg_id]["reaction_sum"] += 1
                        msg = await channel.fetch_message(reaction.message_id)
                        try:
                            await msg.remove_reaction(str(reaction.emoji), reaction.member)
                        except discord.Forbidden:
                            await channel.send('リアクションの除去に失敗しました.')
                        notify_msg = await channel.send(f"{reaction.member.mention} 権限無しのリアクションは禁止です！")
                        # await self.autodel_msg(notify_msg)
                        return

                if "matte" in reaction.emoji.name:
                    self.reaction_dict[msg_id]["matte"] += 1
                    msg = await channel.fetch_message(reaction.message_id)
                    await msg.edit(content=msg.content + "\n待ちます")
                else:
                    self.reaction_dict[msg_id]["reaction_sum"] += 1

                await self.judge_and_notice(msg_id)

    @ commands.Cog.listener()
    async def on_raw_reaction_remove(self, reaction):
        remove_usr = self.bot.get_user(reaction.user_id)
        if remove_usr.bot:
            return
        for msg_id in list(self.reaction_dict):
            if int(msg_id) == reaction.message_id:
                if "matte" in reaction.emoji.name:
                    self.reaction_dict[msg_id]["matte"] -= 1
                    channel = self.bot.get_channel(reaction.channel_id)
                    msg = await channel.fetch_message(reaction.message_id)
                    await msg.edit(content=msg.content.replace("\n待ちます", "", 1))
                else:
                    self.reaction_dict[msg_id]["reaction_sum"] -= 1

                await self.judge_and_notice(msg_id)

    async def remind(self, msg_id, elapsed_time) -> None:
        if self.reaction_dict[msg_id]["matte"] > 0:
            return

        try:
            reminded = self.reaction_dict[msg_id]["reminded"]
        except KeyError:
            reminded = 0

        if reminded > 0:
            return

        channel = self.bot.get_channel(
            self.reaction_dict[msg_id]["channel"])
        url = self.reaction_dict[msg_id]["url"]
        roles = self.reaction_dict[msg_id]["role"]

        if len(roles) == 0:
            roles_mention = 'None'
            roles_name = 'None'
        else:
            roles_mention = [channel.guild.get_role(i).mention for i in roles]
            roles_mention = ' '.join(roles_mention)

            roles_name = [channel.guild.get_role(i).name for i in roles]
            roles_name = ' '.join(roles_name)

        auth = self.reaction_dict[msg_id]["author"]
        reaction_sum = self.reaction_dict[msg_id]["reaction_sum"]
        reaction_cnt = self.reaction_dict[msg_id]["cnt"]

        embed = discord.Embed(title="上記、リマインドします")
        embed.add_field(
            name="詳細",
            value=f"ID : {msg_id} by : {auth} 経過時間 : {elapsed_time} progress : {reaction_sum}/{reaction_cnt}\n{url}",
            inline=False)
        embed.set_footer(text=f"対象の役職 : {roles_name} ID : {msg_id}")

        await channel.send(f"{roles_mention}")
        await channel.send(embed=embed)

        self.reaction_dict[msg_id]['reminded'] = 1
        # self.dump_json(self.reaction_dict)

    @ tasks.loop(seconds=10.0)
    async def reaction_reminder(self) -> None:
        await self.bot.wait_until_ready()

        today = datetime.today()
        now_M = today.strftime('%M')

        if now_M == '00':
            for i in self.reaction_dict.keys():
                start_time = datetime.strptime(
                    self.reaction_dict[i]['time'], '%Y-%m-%d %H:%M:%S')
                elapsed_time = today - start_time
                if elapsed_time.days >= 3:
                    await self.remind(i, elapsed_time)

                await asyncio.sleep(0.3)


def setup(bot):
    bot.add_cog(reaction(bot))

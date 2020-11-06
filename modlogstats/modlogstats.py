import asyncio
import threading
from collections import defaultdict
from datetime import timedelta
from time import sleep
from typing import List, Optional
from datetime import datetime
import discord
from redbot.core import commands, modlog
from redbot.core.i18n import Translator, cog_i18n
from requests import Session

_ = Translator("ModLogStats", __file__)
UPDATE_DELAY = 0.3
tasks = defaultdict(lambda: False)
cases = defaultdict(lambda: 0)


@cog_i18n(_)
class ModLogStats(commands.Cog):
    def __init__(self):
        self.webhooks = defaultdict(lambda: None)

    def cog_unload(self):
        for guild_id in tasks:
            tasks[guild_id] = False
        for guild_id in self.webhooks:
            asyncio.create_task(self.webhooks[guild_id].delete(reason="Cog unload."))

    def red_delete_data_for_user(self, *, requester, user_id):
        return  # This cog stores no EUD

    @commands.bot_has_permissions(manage_webhooks=True)
    @commands.max_concurrency(1, commands.BucketType.guild, wait=False)
    @commands.command()
    async def modlogstats(self, ctx, *, time: Optional[commands.TimedeltaConverter] = None):
        """Get modlog stats for the timeframe specified."""
        message_id = await self._initialize_webhook_message(ctx.channel)
        tasks[ctx.guild.id] = 1
        SendProcessingCasesTask(
            self.webhooks[ctx.guild.id].url, ctx.guild.id, message_id, len(cases)
        ).start()
        modlogcases = await modlog.get_all_cases(ctx.guild, ctx.bot)
        cases[ctx.guild.id] = len(modlogcases)
        tasks[ctx.guild.id] = 2
        counts = defaultdict(int)
        min_date = (datetime.utcnow() - time).timestamp()
        for modlogcase in modlogcases:
            if modlogcase.created_at > min_date:
                counts[modlogcase.action_type] = counts[modlogcase.action_type] + 1
        tasks[ctx.guild.id] = False
        em = discord.Embed(title=_("Results"))
        em.color = discord.Color.green()
        em.set_footer(
            text=_("Total cases: {amount}").format(
                amount=(await modlog.get_latest_case(ctx.guild, ctx.bot)).case_number
            )
        )
        em_list = []
        embed_fields_filled = 0
        for casetype in counts:
            if embed_fields_filled == 25:
                em_list.append(em)
                em = discord.Embed(title=_("Results"))
                em.color = discord.Color.green()
            em.add_field(
                name=(await modlog.get_casetype(casetype)).case_str, value=counts[casetype]
            )
        em_list.append(em)
        await asyncio.sleep(3)
        _edit_webhook_message_embeds(self.webhooks[ctx.guild.id].url, message_id, em_list)

    async def _maybe_create_webhook(self, channel):
        if not self.webhooks[channel.guild.id]:
            self.webhooks[channel.guild.id] = await channel.create_webhook(
                name=_("Modlogstats"), reason=_("Modlogstats status message.")
            )

    async def _initialize_webhook_message(self, channel):
        await self._maybe_create_webhook(channel)
        em = discord.Embed(title="\u200b")
        try:
            await self.webhooks[channel.guild.id].send(embed=em)
        except discord.NotFound:
            self.webhooks[channel.guild.id] = None
            await self._maybe_create_webhook(channel)
            await self.webhooks[channel.guild.id].send(embed=em)
        async for message in channel.history(limit=15, oldest_first=False):
            if message.author.id == self.webhooks[channel.guild.id].id:
                message_id = message.id
                break
        return message_id


class SendProcessingCasesTask(threading.Thread):
    def __init__(self, url, guild_id, message_id, amount_of_cases):
        threading.Thread.__init__(self)
        self.url = url
        self.guild_id = guild_id
        self.message_id = message_id
        self.amount_of_cases = amount_of_cases

    def run(self):
        self._send_waiting_message(self.url, self.guild_id, self.message_id)

    def _send_waiting_message(self, url, guild_id, message_id):
        em = discord.Embed()
        em.set_footer(text=_("This WILL take a while."))
        while tasks[guild_id] == 1:
            sleep(UPDATE_DELAY)
            em.title = _("Getting cases.")
            em.color = discord.Color(0xFFFF66)
            _edit_webhook_message_embeds(url, message_id, [em])
            sleep(UPDATE_DELAY)
            em.title = _("Getting cases..")
            em.color = discord.Color(0x000000)
            _edit_webhook_message_embeds(url, message_id, [em])
            sleep(UPDATE_DELAY)
            em.title = _("Getting cases...")
            em.color = discord.Color(0xFFFF66)
            _edit_webhook_message_embeds(url, message_id, [em])
            sleep(UPDATE_DELAY)
            em.title = _("Getting cases")
            em.color = discord.Color(0x000000)
            _edit_webhook_message_embeds(url, message_id, [em])
        em.set_footer(text=_("This might take a while."))
        amount_of_cases = cases[guild_id]
        while tasks[guild_id] == 2:
            em.title = _("Processing {cases} cases").format(cases=amount_of_cases)
            em.color = discord.Color.dark_green()
            _edit_webhook_message_embeds(url, message_id, [em])
            sleep(UPDATE_DELAY)
            em.title = _("Processing {cases} cases.").format(cases=amount_of_cases)
            em.color = discord.Color(0x000000)
            _edit_webhook_message_embeds(url, message_id, [em])
            sleep(UPDATE_DELAY)
            em.title = _("Processing {cases} cases..").format(cases=amount_of_cases)
            em.color = discord.Color.dark_green()
            _edit_webhook_message_embeds(url, message_id, [em])
            sleep(UPDATE_DELAY)
            em.title = _("Processing {cases} cases...").format(cases=amount_of_cases)
            em.color = discord.Color(0x000000)
            _edit_webhook_message_embeds(url, message_id, [em])
            sleep(UPDATE_DELAY)


# Thanks phenom4n4n, you've been a massive help with this.
def _edit_webhook_message_embeds(url, message_id, embeds: List[discord.Embed]):
    with Session() as session:
        with session.patch(
            f"{url}/messages/{message_id}",
            headers={"Content-Type": "application/json"},
            json={"embeds": [embed.to_dict() for embed in embeds]},
        ):
            pass
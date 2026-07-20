import os
import sys 
import math
import time
import asyncio 
import logging
from .utils import STS
from database import db 
from .test import CLIENT, start_clone_bot
from config import Config, temp
from translation import Translation
from pyrogram import Client, filters 
from pyrogram.errors import FloodWait, MessageNotModified, RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message 

CLIENT = CLIENT()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
TEXT = Translation.TEXT

@Client.on_callback_query(filters.regex(r'^start_public'))
async def pub_(bot, message):
    user = message.from_user.id
    temp.CANCEL[user] = False
    frwd_id = message.data.split("_")[2]
    
    if temp.lock.get(user) and str(temp.lock.get(user)) == "True":
        return await message.answer("Please wait until previous task is complete", show_alert=True)
        
    sts = STS(frwd_id)
    if not sts.verify():
        await message.answer("You are clicking on an old button", show_alert=True)
        return await message.message.delete()
        
    i = sts.get(full=True)
    if i.TO in temp.IS_FRWD_CHAT:
        return await message.answer("In Target chat a task is progressing. Please wait until task is complete", show_alert=True)
        
    m = await msg_edit(message.message, "<code>Verifying your data, please wait...</code>")
    _bot, caption, forward_tag, data, protect, button = await sts.get_data(user)
    
    if not _bot:
        return await msg_edit(m, "<code>You didn't add any bot. Please add a bot using /settings!</code>", wait=True)
        
    try:
        client = await start_clone_bot(CLIENT.client(_bot))
    except Exception as e:  
        return await m.edit(f"<b>Error:</b> {e}")
        
    await msg_edit(m, "<code>Processing...</code>")
    
    try: 
        await client.get_messages(sts.get("FROM"), 1)
    except:
        await msg_edit(m, f"**Source chat may be a private channel / group. Use userbot or Make Your [Bot](t.me/{_bot['username']}) an admin over there**", retry_btn(frwd_id), True)
        return await stop(client, user)
        
    try:
        k = await client.send_message(i.TO, "Testing")
        await k.delete()
    except:
        await msg_edit(m, f"**Please Make Your [UserBot / Bot](t.me/{_bot['username']}) Admin In Target Channel With Full Permissions**", retry_btn(frwd_id), True)
        return await stop(client, user)
        
    temp.forwardings += 1
    await db.add_frwd(user)
    await send(client, user, "<b>🚀 ғᴏʀᴡᴀʀᴅɪɴɢ sᴛᴀʀᴛᴇᴅ!</b>")
    sts.add(time=True)
    
    # [PRO LEVEL UPDATE] Speed Optimization: Bot = ~25 files/sec (0.04s), Userbot = 1 file/sec (1.0s)
    sleep_time = 0.04 if _bot.get('is_bot') else 1.0
    
    await msg_edit(m, "<code>Processing...</code>") 
    temp.IS_FRWD_CHAT.append(i.TO)
    temp.lock[user] = locked = True
    
    if locked:
        try:
            MSG = []
            pling = 0
            await edit(m, 'Progressing', 10, sts)
            print(f"Starting Forwarding Process... From: {sts.get('FROM')} To: {sts.get('TO')} Total: {sts.get('limit')} skip: {sts.get('skip')}")

            is_continuous = getattr(sts, 'continuous', False)

            async for message in client.iter_messages(
                client,
                chat_id=sts.get('FROM'), 
                limit=int(sts.get('limit')), 
                offset=int(sts.get('skip')) if sts.get('skip') else 0,
                continuous=is_continuous
            ):
                if await is_cancelled(client, user, m, sts):
                    return
                if pling % 20 == 0: 
                    await edit(m, 'Progressing', 10, sts)
                pling += 1
                sts.add('fetched')
                
                if message == "DUPLICATE":
                    sts.add('duplicate')
                    continue 
                elif message == "FILTERED":
                    sts.add('filtered')
                    continue 
                if message.empty or message.service:
                    sts.add('deleted')
                    continue
                    
                if forward_tag:
                    MSG.append(message.id)
                    notcompleted = len(MSG)
                    completed = sts.get('total') - sts.get('fetched')
                    
                    if notcompleted >= 100 or completed <= 100: 
                        await forward(client, MSG, m, sts, protect)
                        sts.add('total_files', notcompleted)
                        # [PRO LEVEL UPDATE] Fast batch sleep
                        await asyncio.sleep(0.05)
                        MSG = []
                else:
                    new_caption = custom_caption(message, caption)
                    details = {"msg_id": message.id, "media": media(message), "caption": new_caption, 'button': button, "protect": protect}
                    await copy(client, details, m, sts)
                    sts.add('total_files')
                    await asyncio.sleep(sleep_time) 
                    
        except Exception as e:
            await msg_edit(m, f'<b>ERROR:</b>\n<code>{e}</code>', wait=True)
            if sts.TO in temp.IS_FRWD_CHAT:
                temp.IS_FRWD_CHAT.remove(sts.TO)
            return await stop(client, user)
            
        if sts.TO in temp.IS_FRWD_CHAT:
            temp.IS_FRWD_CHAT.remove(sts.TO)
        await send(client, user, "<b>🎉 ғᴏʀᴡᴀʀᴅɪɴɢ ᴄᴏᴍᴘʟᴇᴛᴇᴅ 🥀</b>")
        await edit(m, 'Completed', "completed", sts) 
        await stop(client, user)
            
async def copy(bot, msg, m, sts):
    try:                                  
        if msg.get("media") and msg.get("caption"):
            await bot.send_cached_media(
                chat_id=sts.get('TO'),
                file_id=msg.get("media"),
                caption=msg.get("caption"),
                reply_markup=msg.get('button'),
                protect_content=msg.get("protect"))
        else:
            await bot.copy_message(
                chat_id=sts.get('TO'),
                from_chat_id=sts.get('FROM'),    
                caption=msg.get("caption"),
                message_id=msg.get("msg_id"),
                reply_markup=msg.get('button'),
                protect_content=msg.get("protect"))
    except FloodWait as e:
        # [PRO LEVEL UPDATE] Anti-Crash Auto Resume Logic
        print(f"FloodWait triggered for {e.value}s in copy.")
        await edit(m, 'Sleeping', e.value, sts)
        await asyncio.sleep(e.value + 1) # Extra 1s padding to be safe
        await edit(m, 'Progressing', 10, sts)
        await copy(bot, msg, m, sts) # Retrying the same message
    except Exception as e:
        print(f"Failed to copy message {msg.get('msg_id')}: {e}")
        sts.add('deleted')
        
async def forward(bot, msg, m, sts, protect):
    try:                             
        await bot.forward_messages(
            chat_id=sts.get('TO'),
            from_chat_id=sts.get('FROM'), 
            protect_content=protect,
            message_ids=msg)
    except FloodWait as e:
        # [PRO LEVEL UPDATE] Anti-Crash Auto Resume Logic
        print(f"FloodWait triggered for {e.value}s in forward.")
        await edit(m, 'Sleeping', e.value, sts)
        await asyncio.sleep(e.value + 1)
        await edit(m, 'Progressing', 10, sts)
        await forward(bot, msg, m, sts, protect) # Retrying the same batch
    except Exception as e:
        print(f"Failed to forward messages {msg}: {e}")
        sts.add('deleted')

PROGRESS = """
📈 Percentage: {0}%

♻️ Fetched: {1}

♻️ Forwarded: {2}

♻️ Remaining: {3}

♻️ Status: {4}

⏳ ETA: {5}
"""

async def msg_edit(msg, text, button=None, wait=None):
    try:
        return await msg.edit(text, reply_markup=button)
    except MessageNotModified:
        pass 
    except FloodWait as e:
        if wait:
            await asyncio.sleep(e.value)
            return await msg_edit(msg, text, button, wait)
        
async def edit(msg, title, status, sts):
    i = sts.get(full=True)
    status = 'Forwarding' if status == 10 else f"Sleeping {status} s" if str(status).isnumeric() else status
    total = float(i.total) if float(i.total) > 0 else 1.0
    percentage = "{:.0f}".format(float(i.fetched)*100/total)
   
    now = time.time()
    diff = int(now - i.start)
    speed = sts.divide(i.fetched, diff)
    elapsed_time = round(diff) * 1000
    time_to_completion = round(sts.divide(i.total - i.fetched, int(speed))) * 1000
    estimated_total_time = elapsed_time + time_to_completion  
    progress = "◉{0}{1}".format(
        ''.join(["◉" for _ in range(math.floor(int(percentage) / 10))]),
        ''.join(["◎" for _ in range(10 - math.floor(int(percentage) / 10))]))
    
    button = [[InlineKeyboardButton(title, f'fwrdstatus#{status}#{estimated_total_time}#{percentage}#{i.id}')]]
    estimated_total_time = TimeFormatter(milliseconds=estimated_total_time)
    estimated_total_time = estimated_total_time if estimated_total_time != '' else '0 s'

    text = TEXT.format(i.fetched, i.total_files, i.duplicate, i.deleted, i.skip, status, percentage, estimated_total_time, progress)
    
    if status in ["cancelled", "completed"]:
        button.append(
            [InlineKeyboardButton('Support', url='https://t.me/dev_gagan'),
             InlineKeyboardButton('Updates', url='https://t.me/dev_gagan')]
        )
    else:
        button.append([InlineKeyboardButton('• ᴄᴀɴᴄᴇʟ', 'terminate_frwd')])
        
    await msg_edit(msg, text, InlineKeyboardMarkup(button))
   
async def is_cancelled(client, user, msg, sts):
    if temp.CANCEL.get(user) == True:
        if sts.TO in temp.IS_FRWD_CHAT:
            temp.IS_FRWD_CHAT.remove(sts.TO)
        await edit(msg, "Cancelled", "completed", sts)
        await send(client, user, "<b>❌ Forwarding Process Cancelled</b>")
        await stop(client, user)
        return True 
    return False 

async def stop(client, user):
    try:
        await client.stop()
    except:
        pass 
    await db.rmve_frwd(user)
    temp.forwardings -= 1
    temp.lock[user] = False 
    
async def send(bot, user, text):
    try:
        await bot.send_message(user, text=text)
    except:
        pass 
     
def custom_caption(msg, caption):
    if msg.media:
        if (msg.video or msg.document or msg.audio or msg.photo):
            media = getattr(msg, msg.media.value, None)
            if media:
                file_name = getattr(media, 'file_name', '')
                file_size = getattr(media, 'file_size', '')
                fcaption = getattr(msg, 'caption', '')
                if fcaption:
                    fcaption = fcaption.html
                if caption:
                    return caption.format(filename=file_name, size=get_size(file_size), caption=fcaption)
                return fcaption
    return None

def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i]) 

def media(msg):
    if msg.media:
        media = getattr(msg, msg.media.value, None)
        if media:
            return getattr(media, 'file_id', None)
    return None 

def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
        ((str(hours) + "h, ") if hours else "") + \
        ((str(minutes) + "m, ") if minutes else "") + \
        ((str(seconds) + "s, ") if seconds else "") + \
        ((str(milliseconds) + "ms, ") if milliseconds else "")
    return tmp[:-2] if tmp else ""

def retry_btn(id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('♻️ RETRY ♻️', f"start_public_{id}")]])

@Client.on_callback_query(filters.regex(r'^terminate_frwd$'))
async def terminate_frwding(bot, m):
    user_id = m.from_user.id 
    temp.lock[user_id] = False
    temp.CANCEL[user_id] = True 
    await m.answer("Forwarding cancelled!", show_alert=True)
          
@Client.on_callback_query(filters.regex(r'^fwrdstatus'))
async def status_msg(bot, msg):
    _, status, est_time, percentage, frwd_id = msg.data.split("#")
    sts = STS(frwd_id)
    if not sts.verify():
        fetched, forwarded, remaining = 0, 0, 0
    else:
        fetched, forwarded = sts.get('fetched'), sts.get('total_files')
        remaining = fetched - forwarded 
    est_time = TimeFormatter(milliseconds=est_time)
    est_time = est_time if (est_time != '' or status not in ['completed', 'cancelled']) else '0 s'
    return await msg.answer(PROGRESS.format(percentage, fetched, forwarded, remaining, status, est_time), show_alert=True)
                  
@Client.on_callback_query(filters.regex(r'^close_btn$'))
async def close(bot, update):
    await update.answer()
    await update.message.delete()

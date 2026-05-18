import os
import re
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from discord import app_commands
import httpx
from datetime import datetime, timezone, timedelta

class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
    def log_message(self, *a): pass

def _run_server():
    HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 8080))), _H).serve_forever()

threading.Thread(target=_run_server, daemon=True).start()

# ── CONFIG ────────────────────────────────────────────────────────────────────
SUPABASE_URL  = os.environ['SUPABASE_URL']
SUPABASE_KEY  = os.environ['SUPABASE_KEY']
LOG_CHANNEL_ID = int(os.environ['LOG_CHANNEL_ID'])
CURRENT_LB_ID  = int(os.environ['CURRENT_LB_ID'])
ALLTIME_LB_ID  = int(os.environ['ALLTIME_LB_ID'])
MEMBERS_ID     = int(os.environ['MEMBERS_ID'])
ROLE_LOG_ID    = int(os.environ.get('ROLE_LOG_ID', '1504206471653621760'))

HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'resolution=merge-duplicates,return=representation'
}

RANKS = ['F','E','D','C','B','A','S','Legend','Angel','GOD']
THRESH = {'F':0,'E':30,'D':70,'C':120,'B':180,'A':250,'S':330,'Legend':420,'Angel':520,'GOD':float('inf')}
RANK_EMOJI = {'F':'','E':'','D':'','C':'','B':'','A':'','S':'','Legend':'🔥','Angel':'🪽','GOD':'🪐'}
ROLE_NAMES = {
    'F':'F Rank','E':'E Rank','D':'D Rank','C':'C Rank','B':'B Rank',
    'A':'A Rank','S':'S Rank','Legend':'Legend Rank 🔥','Angel':'Angel Rank 🪽','GOD':'GOD Rank 🪐'
}
MEDAL = {0:'🥇',1:'🥈',2:'🥉'}

RS_RANKS = ['F', 'E', 'D', 'C', 'B', 'A', 'S']
RS_THRESH = {'F':0,'E':30,'D':70,'C':120,'B':180,'A':250,'S':330}
RS_ROLE_NAMES = {r: f'{r} Rank RS' for r in RS_RANKS}
RS_CURRENT_LB_ID = 1504410991750938644
RS_ALLTIME_LB_ID = 1504411488448807003
RANKED_STYLE_ROLE = 'Ranked Style'
TRUE_POWER_ROLE   = 'True Power'
ELITE_RS_ROLE = 'Elite RS'

DISCORD_ROLES = ['Owner', 'SOD_PVP', 'High Admin', 'Admin Of The Month', 'Admin', 'Manager']
DISCORD_ROLE_LEVEL = {'': 0, 'Manager': 1, 'Admin': 2, 'Admin Of The Month': 3, 'High Admin': 4, 'SOD_PVP': 5, 'Owner': 6}

CMD_DEFAULTS = {
    'pvp':          'owner',
    'addmember':    'owner',
    'removemember': 'owner',
    'unrank':       'owner',
    'rerank':       'owner',
    'sync':         'owner',
    'leaderboard':  'admin',
    'sethandle':    'admin',
    'mystats':      'all',
    'challenge':    'all',
    'accept':       'all',
    'decline':      'all',
    'challenges':   'all',
    'joinleague':   'all',
    'leaveleague':  'all',
    'ascension':    'all',
}

# ── SUPABASE ──────────────────────────────────────────────────────────────────
async def sb_get(table, query=''):
    async with httpx.AsyncClient() as c:
        r = await c.get(f'{SUPABASE_URL}/rest/v1/{table}?{query}', headers=HEADERS)
        r.raise_for_status(); return r.json()

async def sb_upsert(table, data):
    async with httpx.AsyncClient() as c:
        r = await c.post(f'{SUPABASE_URL}/rest/v1/{table}', headers=HEADERS, json=data)
        r.raise_for_status(); return r.json()

async def sb_patch(table, filter_, data):
    async with httpx.AsyncClient() as c:
        r = await c.patch(f'{SUPABASE_URL}/rest/v1/{table}?{filter_}', headers=HEADERS, json=data)
        r.raise_for_status()

async def sb_delete(table, filter_):
    async with httpx.AsyncClient() as c:
        r = await c.delete(f'{SUPABASE_URL}/rest/v1/{table}?{filter_}', headers=HEADERS)
        r.raise_for_status()

async def get_next_join_order():
    players = await sb_get('players', 'select=join_order&order=join_order.desc&limit=1')
    if players and players[0].get('join_order'):
        return players[0]['join_order'] + 1
    return 1

# ── PERMISSION SYSTEM ─────────────────────────────────────────────────────────
async def get_cmd_permission(cmd_name: str) -> str:
    try:
        rows = await sb_get('settings', f'key=eq.cmd_{cmd_name}')
        if rows:
            return rows[0].get('value', CMD_DEFAULTS.get(cmd_name, 'owner'))
    except Exception:
        pass
    return CMD_DEFAULTS.get(cmd_name, 'owner')

def has_role(interaction: discord.Interaction, role_name: str) -> bool:
    if not interaction.guild: return False
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    return role in interaction.user.roles if role else False

async def check_permission(interaction: discord.Interaction, cmd_name: str) -> bool:
    level = await get_cmd_permission(cmd_name)
    if level == 'all':
        return True
    if level == 'admin':
        if has_role(interaction, 'Owner') or has_role(interaction, 'Admin'):
            return True
        await interaction.followup.send('❌ This command requires **Admin** or **Owner** role.', ephemeral=True)
        return False
    if has_role(interaction, 'Owner'):
        return True
    await interaction.followup.send('❌ This command requires the **Owner** role.', ephemeral=True)
    return False

# ── GAME LOGIC ────────────────────────────────────────────────────────────────
def rank_idx(r): return RANKS.index(r) if r in RANKS else 0

def points_win(wr, lr, score):
    gap = rank_idx(wr) - rank_idx(lr)
    pts = 25 if gap<=-2 else 18 if gap==-1 else 10 if gap==0 else 4 if gap==1 else 1
    if score=='3-0': pts+=3
    elif score=='3-1': pts+=1
    return pts

def points_loss(wr, lr):
    # gap>0 = winner higher rank, loser loses only 2pts
    # gap<0 = winner lower rank, loser loses 12pts
    gap = rank_idx(wr) - rank_idx(lr)
    return 12 if gap<0 else 5 if gap==0 else 2

def rs_rank_idx(r): return RS_RANKS.index(r) if r in RS_RANKS else 0

def points_rs_win(wr, lr, score):
    gap = rs_rank_idx(wr) - rs_rank_idx(lr)
    pts = 25 if gap<=-2 else 18 if gap==-1 else 10 if gap==0 else 4 if gap==1 else 1
    if score=='3-0': pts+=3
    elif score=='3-1': pts+=1
    return pts

def points_rs_loss(wr, lr):
    gap = rs_rank_idx(wr) - rs_rank_idx(lr)
    return 12 if gap<0 else 5 if gap==0 else 2

# ── CHALLENGE HELPERS ─────────────────────────────────────────────────────────
CHALLENGE_EXPIRY_DAYS = 7

def forfeit_points_win(challenger_rank, defender_rank):
    """Points challenger gains on forfeit/decline (3-0 equivalent)."""
    return points_win(challenger_rank, defender_rank, '3-0')

def forfeit_points_loss(challenger_rank, defender_rank):
    """Points decliner/forfeiter loses (same as normal loss)."""
    return points_loss(challenger_rank, defender_rank)

async def get_open_challenge(challenger_key, defender_key):
    """Return open challenge between two players in either direction."""
    rows = await sb_get('challenges',
        f'challenger_key=eq.{challenger_key}&defender_key=eq.{defender_key}&status=eq.pending')
    return rows[0] if rows else None

async def get_pending_as_defender(defender_key):
    """All pending challenges where this player is the defender."""
    return await sb_get('challenges', f'defender_key=eq.{defender_key}&status=eq.pending')

async def get_pending_as_challenger(challenger_key):
    """All pending challenges where this player is the challenger."""
    return await sb_get('challenges', f'challenger_key=eq.{challenger_key}&status=eq.pending')

async def can_rechallenge(challenger_key, defender_key, challenger_rank, defender_rank):
    """
    Returns (allowed: bool, reason: str).
    Block if last challenge/match between them exists AND neither rank has changed since.
    """
    # Check challenges table for last interaction
    rows = await sb_get('challenges',
        f'or=(and(challenger_key.eq.{challenger_key},defender_key.eq.{defender_key}),'
        f'and(challenger_key.eq.{defender_key},defender_key.eq.{challenger_key}))'
        f'&status=in.(completed,declined,expired,forfeited)'
        f'&order=created_at.desc&limit=1')
    if not rows:
        return True, ''
    last = rows[0]
    # If either rank changed since that challenge, allow
    if (last.get('challenger_rank_at_time') != challenger_rank or
            last.get('defender_rank_at_time') != defender_rank):
        return True, ''
    return False, f'You already challenged this player recently. Wait until either rank changes, or they challenge you first.'

async def apply_forfeit(guild, challenger, defender):
    """Apply forfeit points: defender loses, challenger gains. challenger/defender are player dicts."""
    cr, dr = challenger['rank'], defender['rank']
    gain = forfeit_points_win(cr, dr)
    lose = forfeit_points_loss(cr, dr)
    challenger['points'] = max(0, challenger.get('points', 0) + gain)
    challenger['wins'] = challenger.get('wins', 0) + 1
    challenger['streak'] = max(0, challenger.get('streak', 0)) + 1
    defender['points'] = max(0, defender.get('points', 0) - lose)
    defender['losses'] = defender.get('losses', 0) + 1
    defender['streak'] = min(0, defender.get('streak', 0)) - 1
    await sb_upsert('players', [challenger, defender])
    return gain, lose

# ── DISCORD HANDLE → MENTION ──────────────────────────────────────────────────
def fmt_handle(handle, guild):
    if not handle: return ''
    clean = handle.lstrip('@')
    if guild:
        member = discord.utils.find(
            lambda m: m.name==clean or str(m)==clean or (m.nick and m.nick==clean),
            guild.members)
        if member:
            return member.mention
    return handle

# ── BUILD POSTS ───────────────────────────────────────────────────────────────
async def build_current_lb(guild=None):
    players = await sb_get('players', 'order=points.desc')
    ranked = [p for p in players if not p.get('unranked', False)]
    lines = ['**```Current Leaderboard```**\n']
    groups = []
    for p in ranked:
        pts = p.get('points', 0)
        if pts > 0 and groups and groups[-1][0] == pts:
            groups[-1][1].append(p)
        else:
            groups.append((pts, [p]))
    display_pos = 0
    for pts, group in groups:
        pos = display_pos
        medal = MEDAL.get(pos, f'#{pos+1}')
        if len(group) > 1:
            parts = []
            for p in group:
                handle = fmt_handle(p.get('discord_handle', ''), guild)
                flag = p.get('flag', '')
                part = p['name']
                if flag: part += f' {flag}'
                if handle: part += f' {handle}'
                parts.append(part)
            line = f'> {medal}  ' + ' / '.join(parts)
            if pts > 0: line += f'  [ *{pts} Points* ]'
            rank_e = RANK_EMOJI.get(group[0]['rank'], '')
            if rank_e: line += f' {rank_e}'
            lines.append(line); lines.append('> ')
        else:
            p = group[0]
            flag   = p.get('flag', '')
            handle = fmt_handle(p.get('discord_handle', ''), guild)
            rank_e = RANK_EMOJI.get(p['rank'], '')
            line   = f'> {medal}  {p["name"]} {flag}'
            if handle: line += f'  {handle}'
            if rank_e: line += f' {rank_e}'
            if pts > 0: line += f'  [ *{pts} Points* ]'
            lines.append(line); lines.append('> ')
        display_pos += 1
    return '\n'.join(lines)

async def build_alltime_lb(guild=None):
    players = await sb_get('players', 'order=points.desc')
    ranked = [p for p in players if not p.get('unranked', False)]
    ranked.sort(key=lambda p: (-rank_idx(p['rank']), -p.get('points', 0)))
    lines = ['**```All Time Leaderboard```**\n']
    groups = []
    for p in ranked:
        pts = p.get('points', 0)
        key = (p['rank'], pts)
        if pts > 0 and groups and groups[-1][0] == key:
            groups[-1][1].append(p)
        else:
            groups.append((key, [p]))
    display_pos = 0
    for (rank, pts), group in groups:
        pos = display_pos
        medal = MEDAL.get(pos, f'#{pos+1}')
        rank_e = RANK_EMOJI.get(rank, '')
        if len(group) > 1:
            parts = []
            for p in group:
                handle = fmt_handle(p.get('discord_handle', ''), guild)
                flag = p.get('flag', '')
                part = p['name']
                if flag: part += f' {flag}'
                if handle: part += f' {handle}'
                parts.append(part)
            line = f'> {medal}  ' + ' / '.join(parts)
            if pts > 0: line += f'  [ *{pts} Points* ]'
            line += f'  **{rank} Rank**'
            if rank_e: line += f' {rank_e}'
            lines.append(line); lines.append('> ')
        else:
            p = group[0]
            flag   = p.get('flag', '')
            handle = fmt_handle(p.get('discord_handle', ''), guild)
            line   = f'> {medal}  {p["name"]} {flag}'
            if handle: line += f'  {handle}'
            line  += f'  **{rank} Rank**'
            if rank_e: line += f' {rank_e}'
            if pts > 0: line += f'  [ *{pts} Points* ]'
            lines.append(line); lines.append('> ')
        display_pos += 1
    return '\n'.join(lines)

async def build_rs_current_lb(guild=None):
    players = await sb_get('players', 'order=rs_points.desc')
    ranked = [p for p in players if p.get('in_rs', False) and not p.get('rs_unranked', False)]
    lines = ['**```RS Current Leaderboard```**\n']
    groups = []
    for p in ranked:
        pts = p.get('rs_points', 0)
        if pts > 0 and groups and groups[-1][0] == pts:
            groups[-1][1].append(p)
        else:
            groups.append((pts, [p]))
    display_pos = 0
    for pts, group in groups:
        pos = display_pos
        medal = MEDAL.get(pos, f'#{pos+1}')
        if len(group) > 1:
            parts = []
            for p in group:
                handle = fmt_handle(p.get('discord_handle', ''), guild)
                flag = p.get('flag', '')
                part = p['name']
                if flag: part += f' {flag}'
                if handle: part += f' {handle}'
                if p.get('is_elite'): part += ' ⭐'
                parts.append(part)
            line = f'> {medal}  ' + ' / '.join(parts)
            if pts > 0: line += f'  [ *{pts} Points* ]'
            line += f'  **{group[0].get("rs_rank","F")} Rank RS**'
            lines.append(line); lines.append('> ')
        else:
            p = group[0]
            flag   = p.get('flag', '')
            handle = fmt_handle(p.get('discord_handle', ''), guild)
            elite  = ' ⭐' if p.get('is_elite') else ''
            line   = f'> {medal}  {p["name"]} {flag}'
            if handle: line += f'  {handle}'
            line += f'{elite}  **{p.get("rs_rank","F")} Rank RS**'
            if pts > 0: line += f'  [ *{pts} Points* ]'
            lines.append(line); lines.append('> ')
        display_pos += 1
    return '\n'.join(lines)

async def build_rs_alltime_lb(guild=None):
    players = await sb_get('players', 'order=rs_points.desc')
    ranked = [p for p in players if p.get('in_rs', False) and not p.get('rs_unranked', False)]
    ranked.sort(key=lambda p: (-rs_rank_idx(p.get('rs_rank','F')), -p.get('rs_points', 0)))
    lines = ['**```RS All Time Leaderboard```**\n']
    groups = []
    for p in ranked:
        pts = p.get('rs_points', 0)
        key = (p.get('rs_rank','F'), pts)
        if pts > 0 and groups and groups[-1][0] == key:
            groups[-1][1].append(p)
        else:
            groups.append((key, [p]))
    display_pos = 0
    for (rs_rank, pts), group in groups:
        pos = display_pos
        medal = MEDAL.get(pos, f'#{pos+1}')
        if len(group) > 1:
            parts = []
            for p in group:
                handle = fmt_handle(p.get('discord_handle', ''), guild)
                flag = p.get('flag', '')
                part = p['name']
                if flag: part += f' {flag}'
                if handle: part += f' {handle}'
                if p.get('is_elite'): part += ' ⭐'
                parts.append(part)
            line = f'> {medal}  ' + ' / '.join(parts)
            if pts > 0: line += f'  [ *{pts} Points* ]'
            line += f'  **{rs_rank} Rank RS**'
            lines.append(line); lines.append('> ')
        else:
            p = group[0]
            flag   = p.get('flag', '')
            handle = fmt_handle(p.get('discord_handle', ''), guild)
            elite  = ' ⭐' if p.get('is_elite') else ''
            line   = f'> {medal}  {p["name"]} {flag}'
            if handle: line += f'  {handle}'
            line += f'{elite}  **{rs_rank} Rank RS**'
            if pts > 0: line += f'  [ *{pts} Points* ]'
            lines.append(line); lines.append('> ')
        display_pos += 1
    return '\n'.join(lines)

async def build_members_post(guild=None):
    players = await sb_get('players', 'order=join_order.asc')
    role_order = ['Owner', 'High Admin', 'Admin', 'Admin Of The Month', 'Manager']
    buckets = {r: [] for r in role_order}
    rest = []
    for p in players:
        dr = p.get('discord_role', '')
        if dr in buckets: buckets[dr].append(p)
        else: rest.append(p)
    ordered = []
    for r in role_order:
        ordered += buckets[r]
    ordered += rest
    role_tag_map = {
        'Owner':            ' (Owner)',
        'High Admin':       ' (High Admin)',
        'Admin':            ' (Admin)',
        'Admin Of The Month': ' (Admin Of The Month)',
        'Manager':          ' (Manager)',
    }
    lines = []
    for i, p in enumerate(ordered):
        is_unranked = p.get('unranked', False)
        rank_e = '' if is_unranked else RANK_EMOJI.get(p['rank'], '')
        suffix = f' {rank_e}' if rank_e else ''
        unranked_tag = ' *(Unranked)*' if is_unranked else ''
        role_tag = role_tag_map.get(p.get('discord_role', ''), '')
        handle = fmt_handle(p.get('discord_handle', ''), guild)
        handle_str = f' {handle}' if handle else ''
        lines.append(f'**{i+1}. {p["name"]}{suffix}{handle_str}{role_tag}{unranked_tag}**')
    return '\n'.join(lines)

# ── UPDATE DISCORD POSTS ──────────────────────────────────────────────────────
LB_MSG_IDS = {}

async def update_post(channel_id, content):
    channel = bot.get_channel(channel_id)
    if not channel:
        try: channel = await bot.fetch_channel(channel_id)
        except: print(f'Cannot find channel {channel_id}'); return
    if channel_id in LB_MSG_IDS:
        try:
            msg = await channel.fetch_message(LB_MSG_IDS[channel_id])
            await msg.edit(content=content); return
        except: pass
    async for msg in channel.history(limit=20):
        if msg.author == bot.user:
            LB_MSG_IDS[channel_id] = msg.id
            await msg.edit(content=content); return
    msg = await channel.send(content)
    LB_MSG_IDS[channel_id] = msg.id

async def find_member(guild, discord_handle):
    """Find a guild member by stored handle using cache → gateway query → REST search."""
    if not discord_handle: return None
    clean = discord_handle.lstrip('@')
    def _match(m):
        return m.name.lower() == clean.lower() or (m.nick and m.nick.lower() == clean.lower())
    # 1. In-memory cache
    member = discord.utils.find(_match, guild.members)
    if member: return member
    # 2. Gateway query (works without privileged Members intent)
    try:
        results = await guild.query_members(query=clean, limit=10)
        member = discord.utils.find(_match, results)
        if member: return member
    except Exception as e:
        print(f'[find_member] query_members error: {e}')
    # 3. Discord REST search (no special intent required)
    try:
        from discord.http import Route
        route = Route('GET', '/guilds/{guild_id}/members/search', guild_id=guild.id)
        data = await guild._state.http.request(route, params={'query': clean, 'limit': 10})
        for m_data in data:
            user = m_data.get('user', {})
            nick = m_data.get('nick') or ''
            if user.get('username', '').lower() == clean.lower() or nick.lower() == clean.lower():
                mid = int(user['id'])
                member = guild.get_member(mid)
                if not member:
                    try: member = await guild.fetch_member(mid)
                    except: pass
                if member: return member
    except Exception as e:
        print(f'[find_member] REST search error: {e}')
    print(f'[find_member] not found: {discord_handle!r} | cache={len(guild.members)} members')
    return None

def find_guild_role(guild, name):
    """Find a role by name: exact → case-insensitive → emoji-stripped fallback."""
    role = discord.utils.get(guild.roles, name=name)
    if role: return role
    role = discord.utils.find(lambda r: r.name.lower() == name.lower(), guild.roles)
    if role: return role
    stripped = re.sub(r'[^\w\s]', '', name).strip().lower()
    return discord.utils.find(lambda r: re.sub(r'[^\w\s]', '', r.name).strip().lower() == stripped, guild.roles)

async def _add_role_with_retry(member, role, action='add'):
    for attempt in range(3):
        try:
            if action == 'add':
                await member.add_roles(role, reason='PvP rank sync')
            else:
                await member.remove_roles(role, reason='PvP rank sync')
            await asyncio.sleep(0.4)
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                wait = getattr(e, 'retry_after', 5) + 0.5
                print(f'[role_sync] 429 on {member.name}, retrying in {wait}s')
                await asyncio.sleep(wait)
            elif e.status == 403:
                print(f'[role_sync] FORBIDDEN — bot needs Manage Roles permission above rank roles in hierarchy')
                return False
            else:
                print(f'[role_sync] error {action} role {role.name} on {member.name}: {e}')
                return False
    return False

async def update_discord_role(guild, discord_handle, new_rank, discord_role='', unranked=False):
    if not discord_handle or not guild: return
    member = await find_member(guild, discord_handle)
    if not member:
        return
    # Remove all rank roles the member currently holds
    rank_roles = [find_guild_role(guild, n) for n in ROLE_NAMES.values()]
    rank_roles = [r for r in rank_roles if r and r in member.roles]
    for role in rank_roles:
        if not await _add_role_with_retry(member, role, 'remove'):
            return  # stop if we hit a 403 (hierarchy/permission issue)
    # Assign new rank role
    if not unranked:
        new_role = find_guild_role(guild, ROLE_NAMES.get(new_rank, ''))
        if new_role:
            await _add_role_with_retry(member, new_role, 'add')
            print(f'[role_sync] {member.name} → {new_role.name}')
        else:
            guild_roles = [r.name for r in guild.roles]
            print(f'[role_sync] rank role not found for {new_rank!r} | guild roles: {guild_roles}')
    else:
        print(f'[role_sync] {member.name} unranked — rank role removed')
    # Re-apply admin/owner role if needed
    for role_name in (['Owner'] if discord_role == 'Owner' else ['Admin'] if discord_role == 'Admin' else []):
        r = find_guild_role(guild, role_name)
        if r and r not in member.roles:
            try: await member.add_roles(r)
            except: pass

async def update_discord_rs_role(guild, discord_handle, new_rs_rank, unranked=False):
    if not discord_handle or not guild: return
    member = await find_member(guild, discord_handle)
    if not member: return
    # Remove all RS rank roles
    rs_rank_roles = [find_guild_role(guild, n) for n in RS_ROLE_NAMES.values()]
    rs_rank_roles = [r for r in rs_rank_roles if r and r in member.roles]
    for role in rs_rank_roles:
        if not await _add_role_with_retry(member, role, 'remove'):
            return
    # Ensure Ranked Style role
    rs_base = find_guild_role(guild, RANKED_STYLE_ROLE)
    if rs_base and rs_base not in member.roles:
        await _add_role_with_retry(member, rs_base, 'add')
    # Assign new RS rank role
    if not unranked:
        new_role = find_guild_role(guild, RS_ROLE_NAMES.get(new_rs_rank, ''))
        if new_role:
            await _add_role_with_retry(member, new_role, 'add')
            print(f'[rs_role_sync] {member.name} → {new_role.name}')

async def sync_all_rs_roles(guild):
    if not guild: return
    players = await sb_get('players', 'order=join_order.asc')
    rs_players = [p for p in players if p.get('in_rs', False)]
    print(f'[sync_all_rs_roles] syncing {len(rs_players)} RS players')
    for p in rs_players:
        handle = p.get('discord_handle', '')
        if not handle: continue
        try:
            await update_discord_rs_role(
                guild, handle,
                p.get('rs_rank', 'F'),
                unranked=bool(p.get('rs_unranked', False))
            )
            await asyncio.sleep(1)
        except Exception as e:
            print(f'[sync_all_rs_roles] ERROR on {p.get("name")}: {e}')
    print('[sync_all_rs_roles] done')

async def update_elite(guild):
    """Update Elite RS title after any RS stat change."""
    try:
        all_players = await sb_get('players', 'order=rs_points.desc')
        s_players = [p for p in all_players if p.get('in_rs', False) and not p.get('rs_unranked', False) and p.get('rs_rank') == 'S']
        old_elites = [p for p in all_players if p.get('is_elite', False)]
        new_elite = s_players[0] if s_players else None
        old_elite = old_elites[0] if old_elites else None

        if old_elite and new_elite and old_elite['key'] == new_elite['key']:
            return  # No change

        # Remove old elite
        if old_elite:
            await sb_patch('players', f'key=eq.{old_elite["key"]}', {'is_elite': False})
            if guild:
                member = await find_member(guild, old_elite.get('discord_handle', ''))
                if member:
                    elite_role = find_guild_role(guild, ELITE_RS_ROLE)
                    if elite_role and elite_role in member.roles:
                        await _add_role_with_retry(member, elite_role, 'remove')

        # Assign new elite
        if new_elite:
            await sb_patch('players', f'key=eq.{new_elite["key"]}', {'is_elite': True})
            if guild:
                member = await find_member(guild, new_elite.get('discord_handle', ''))
                if member:
                    elite_role = find_guild_role(guild, ELITE_RS_ROLE)
                    if elite_role:
                        await _add_role_with_retry(member, elite_role, 'add')
            log_ch = bot.get_channel(LOG_CHANNEL_ID)
            if log_ch:
                dethrone = f' — dethroning **{old_elite["name"]}**' if old_elite else ''
                await log_ch.send(
                    f'⭐ **Elite RS title changed!** **{new_elite["name"]}** is now the **Elite RS** '
                    f'({new_elite.get("rs_points", 0)} pts){dethrone}')
        elif old_elite:
            log_ch = bot.get_channel(LOG_CHANNEL_ID)
            if log_ch:
                await log_ch.send(f'⭐ **Elite RS title is now vacant** — **{old_elite["name"]}** no longer holds it.')
    except Exception as e:
        print(f'[update_elite] error: {e}')

async def sync_discord_roles_from_guild(guild):
    """Read actual Discord roles for every player, patch discord_role and league flags in DB.
    Returns True if any admin role changed (Members post needs rebuild)."""
    if not guild: return False
    players = await sb_get('players', 'order=join_order.asc')
    changed = False

    # Resolve league roles once by ID (handles emoji in role names like "Ranked Style 🥇")
    rs_role = find_guild_role(guild, RANKED_STYLE_ROLE)
    tp_role = find_guild_role(guild, TRUE_POWER_ROLE)
    print(f'[role_from_guild] RS role: {rs_role}  TP role: {tp_role}')

    for p in players:
        handle = p.get('discord_handle', '')
        if not handle:
            continue
        member = await find_member(guild, handle)
        if not member:
            continue
        member_role_ids = {r.id for r in member.roles}

        # ── Sync admin/display role ────────────────────────────────────────────
        actual_role = get_player_discord_role(member)
        stored_role = p.get('discord_role', '')
        if actual_role != stored_role:
            print(f'[role_from_guild] {p["name"]}: {stored_role!r} → {actual_role!r}')
            try:
                await sb_patch('players', f'key=eq.{p["key"]}', {'discord_role': actual_role})
                await log_role_change(guild, p['name'], stored_role, actual_role)
                changed = True
            except Exception as e:
                print(f'[role_from_guild] patch error for {p["name"]}: {e}')

        # ── Sync RS league membership (add-only, ID-based) ────────────────────
        has_rs_role = bool(rs_role and rs_role.id in member_role_ids)
        if has_rs_role and not p.get('in_rs', False):
            print(f'[role_from_guild] {p["name"]}: has Ranked Style role → joining RS')
            try:
                await sb_patch('players', f'key=eq.{p["key"]}', {
                    'in_rs': True, 'rs_rank': p.get('rs_rank') or 'F',
                    'rs_points': p.get('rs_points') or 0,
                })
                await update_discord_rs_role(guild, handle, p.get('rs_rank') or 'F',
                                             unranked=bool(p.get('rs_unranked', False)))
            except Exception as e:
                print(f'[role_from_guild] RS join patch error for {p["name"]}: {e}')
        # Never auto-remove from RS — removal is manual only

        # ── Sync TP league membership (add-only, ID-based) ────────────────────
        has_tp_role = bool(tp_role and tp_role.id in member_role_ids)
        if has_tp_role and not p.get('in_tp', False):
            print(f'[role_from_guild] {p["name"]}: has True Power role → joining TP')
            try:
                await sb_patch('players', f'key=eq.{p["key"]}', {
                    'in_tp': True, 'rank': p.get('rank') or 'F',
                    'points': p.get('points') or 0,
                })
                await update_discord_role(guild, handle, p.get('rank') or 'F',
                                          actual_role, unranked=bool(p.get('unranked', False)))
            except Exception as e:
                print(f'[role_from_guild] TP join patch error for {p["name"]}: {e}')
        # Never auto-remove from TP — removal is manual only

        await asyncio.sleep(0.2)
    return changed

async def sync_league_from_roles(guild, log_channel=None):
    """Add players to RS/TP leagues based on their Discord roles.
    Only ever ADDS to a league — never removes (removal is manual only)."""
    if not guild: return

    players = await sb_get('players', 'select=*')
    player_by_key    = {p['key']: p for p in players}
    player_by_handle = {
        (p.get('discord_handle') or '').lstrip('@').lower(): p
        for p in players if p.get('discord_handle')
    }

    rs_role = find_guild_role(guild, RANKED_STYLE_ROLE)
    tp_role = find_guild_role(guild, TRUE_POWER_ROLE)
    print(f'[sync_league] RS role: {rs_role}  TP role: {tp_role}')

    # Collect members — API first, cache fallback
    all_members = []
    try:
        async for m in guild.fetch_members(limit=None):
            all_members.append(m)
        print(f'[sync_league] fetched {len(all_members)} members via API')
    except Exception as e:
        print(f'[sync_league] fetch_members failed ({e}), using cache ({len(guild.members)})')
        all_members = list(guild.members)

    fixed = []
    for member in all_members:
        uname = member.name.lower()
        p = player_by_key.get(uname) or player_by_handle.get(uname)
        if not p:
            continue

        member_role_ids = {r.id for r in member.roles}
        patch = {}

        # Only add — never remove based on role detection
        if rs_role and rs_role.id in member_role_ids and not p.get('in_rs', False):
            patch['in_rs'] = True
        if tp_role and tp_role.id in member_role_ids and not p.get('in_tp', False):
            patch['in_tp'] = True

        if not patch:
            continue

        print(f'[sync_league] {p["name"]}: {patch}')
        try:
            await sb_patch('players', f'key=eq.{p["key"]}', patch)
            handle = f'@{member.name}'
            if patch.get('in_rs'):
                await update_discord_rs_role(guild, handle,
                                             p.get('rs_rank') or 'F',
                                             unranked=bool(p.get('rs_unranked', False)))
            if patch.get('in_tp'):
                await update_discord_role(guild, handle,
                                          p.get('rank') or 'F',
                                          p.get('discord_role', ''),
                                          unranked=bool(p.get('unranked', False)))
            fixed.append(f'{p["name"]} → {patch}')
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f'[sync_league] patch error for {p["name"]}: {e}')

    print(f'[sync_league] done — {len(fixed)} updated')
    if log_channel and fixed:
        await log_channel.send(f'✅ **League sync** — {len(fixed)} player(s) added to leagues:\n' +
                               '\n'.join(f'• {f}' for f in fixed))
    elif log_channel:
        await log_channel.send('✅ **League sync** — everyone already in the correct leagues.')

# ── FIX: sync roles with delay between members ───────────────────────────────
async def sync_all_roles(guild):
    if not guild: return
    players = await sb_get('players', 'order=join_order.asc')
    print(f'[sync_all_roles] syncing {len(players)} players')
    for p in players:
        handle = p.get('discord_handle', '')
        if not handle:
            print(f'[sync_all_roles] skipping {p.get("name")} — no handle')
            continue
        try:
            await update_discord_role(
                guild, handle,
                p.get('rank', 'F'),
                p.get('discord_role', ''),
                unranked=bool(p.get('unranked', False))
            )
            await asyncio.sleep(1)  # 1s gap between members to avoid 429 floods
        except Exception as e:
            print(f'[sync_all_roles] ERROR on {p.get("name")}: {e}')
    print('[sync_all_roles] done')
    await sync_all_rs_roles(guild)  # also sync RS roles

async def update_all_posts(guild=None):
    if guild:
        await sync_league_from_roles(guild)
    await update_post(CURRENT_LB_ID,    await build_current_lb(guild))
    await update_post(ALLTIME_LB_ID,    await build_alltime_lb(guild))
    await update_post(RS_CURRENT_LB_ID, await build_rs_current_lb(guild))
    await update_post(RS_ALLTIME_LB_ID, await build_rs_alltime_lb(guild))
    await update_post(MEMBERS_ID,       await build_members_post(guild))
    if guild:
        await sync_all_roles(guild)

async def enforce_roles(guild):
    """Enforce correct Discord roles for every member:
    - Remove Elite RS from anyone who has it without qualifying (scans ALL guild members)
    - Re-add True Power / Ranked Style base roles for in-league players
    - Fix proper Elite RS assignment via update_elite()
    """
    if not guild: return
    rs_role    = find_guild_role(guild, RANKED_STYLE_ROLE)
    tp_role    = find_guild_role(guild, TRUE_POWER_ROLE)
    elite_role = find_guild_role(guild, ELITE_RS_ROLE)
    print(f'[enforce_roles] roles found — TP:{tp_role} RS:{rs_role} Elite:{elite_role}')

    players = await sb_get('players', 'select=*')
    elite_keys = {p['key'] for p in players if p.get('is_elite', False)}
    player_by_key    = {p['key']: p for p in players}
    player_by_handle = {
        (p.get('discord_handle') or '').lstrip('@').lower(): p
        for p in players if p.get('discord_handle')
    }

    # Fetch every guild member (API-direct, same as sync_league_from_roles)
    all_members = []
    try:
        async for m in guild.fetch_members(limit=None):
            all_members.append(m)
        print(f'[enforce_roles] fetched {len(all_members)} guild members')
    except Exception as e:
        print(f'[enforce_roles] fetch_members failed ({e}), using cache')
        all_members = list(guild.members)

    for member in all_members:
        uname = member.name.lower()
        p = player_by_key.get(uname) or player_by_handle.get(uname)
        member_role_ids = {r.id for r in member.roles}

        # Strip Elite RS from ANYONE who has it but isn't the real elite in DB
        if elite_role and elite_role.id in member_role_ids:
            pkey = p['key'] if p else None
            if pkey not in elite_keys:
                print(f'[enforce_roles] {member.name}: has Elite RS without qualifying → removing')
                await _add_role_with_retry(member, elite_role, 'remove')

        if not p:
            continue

        # Re-add TP base role if player is in TP but missing the role.
        # Use "is not False" because in_tp=null (old players) should default to in-TP.
        if p.get('in_tp') is not False and not p.get('unranked', False):
            if tp_role and tp_role.id not in member_role_ids:
                print(f'[enforce_roles] {p["name"]}: missing TP role → re-adding')
                await _add_role_with_retry(member, tp_role, 'add')

        # Re-add RS base role if player is in RS but missing the role
        if p.get('in_rs', False) and not p.get('rs_unranked', False):
            if rs_role and rs_role.id not in member_role_ids:
                print(f'[enforce_roles] {p["name"]}: missing RS role → re-adding')
                await _add_role_with_retry(member, rs_role, 'add')

        await asyncio.sleep(0.1)

    # Assign Elite RS to the correct person (highest-points S-rank RS player)
    await update_elite(guild)
    print('[enforce_roles] done')

# ── SELF-PING (keeps Render from sleeping) ────────────────────────────────────
async def self_ping():
    url = os.environ.get('RENDER_EXTERNAL_URL', 'https://sod-rank-bot.onrender.com')
    while True:
        await asyncio.sleep(240)
        try:
            async with httpx.AsyncClient() as c:
                await c.get(url, timeout=10)
            print('[self_ping] ok')
        except Exception as e:
            print(f'[self_ping] error: {e}')

# ── BOT SETUP ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def periodic_role_sync():
    """Every 20 minutes: read Discord roles → patch DB → sync rank roles → rebuild posts."""
    await bot.wait_until_ready()
    await asyncio.sleep(120)  # let startup settle first
    while not bot.is_closed():
        try:
            guild = next(iter(bot.guilds), None)
            if guild:
                print('[periodic_sync] syncing league memberships from Discord roles...')
                await sync_league_from_roles(guild)
                print('[periodic_sync] reading admin roles from guild...')
                role_changed = await sync_discord_roles_from_guild(guild)
                print('[periodic_sync] syncing rank roles...')
                await sync_all_roles(guild)
                print('[periodic_sync] enforcing base roles and Elite RS...')
                await enforce_roles(guild)
                if role_changed:
                    print('[periodic_sync] discord_role change detected — rebuilding posts')
                    await update_post(MEMBERS_ID, await build_members_post(guild))
                else:
                    await update_post(CURRENT_LB_ID,    await build_current_lb(guild))
                    await update_post(ALLTIME_LB_ID,    await build_alltime_lb(guild))
                    await update_post(RS_CURRENT_LB_ID, await build_rs_current_lb(guild))
                    await update_post(RS_ALLTIME_LB_ID, await build_rs_alltime_lb(guild))
                    await update_post(MEMBERS_ID,       await build_members_post(guild))
        except Exception as e:
            print(f'[periodic_sync] error: {e}')
        await asyncio.sleep(1200)  # every 20 minutes

@bot.event
async def on_ready():
    print(f'NinjaPvP bot online as {bot.user}')
    try:
        for cmd, level in CMD_DEFAULTS.items():
            existing = await sb_get('settings', f'key=eq.cmd_{cmd}')
            if not existing:
                await sb_upsert('settings', [{'key': f'cmd_{cmd}', 'value': level}])
    except Exception as e:
        print(f'[settings init] {e}')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} slash commands globally')
    except Exception as e:
        print(f'Slash sync error: {e}')
    guild = next(iter(bot.guilds), None)
    if guild and not guild.chunked:
        try:
            await guild.chunk()
            print(f'[on_ready] member cache populated: {len(guild.members)} members')
        except Exception as e:
            print(f'[on_ready] chunk failed (enable Server Members Intent in Dev Portal): {e}')
    asyncio.create_task(update_all_posts(guild))
    asyncio.create_task(challenge_expiry_loop())
    asyncio.create_task(self_ping())
    asyncio.create_task(periodic_role_sync())

# ── CHALLENGE EXPIRY SCHEDULER ────────────────────────────────────────────────
async def challenge_expiry_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await process_expired_challenges()
        except Exception as e:
            print(f'[expiry_loop] {e}')
        await asyncio.sleep(3600)  # check every hour

async def process_expired_challenges():
    now = datetime.now(timezone.utc).isoformat()
    expired = await sb_get('challenges',
        f'status=eq.pending&expires_at=lt.{now}')
    if not expired:
        return
    guild = None
    for g in bot.guilds:
        guild = g; break
    log_ch = bot.get_channel(LOG_CHANNEL_ID)
    for ch in expired:
        ckey, dkey = ch['challenger_key'], ch['defender_key']
        players = await sb_get('players', f'key=in.("{ckey}","{dkey}")')
        pmap = {p['key']: p for p in players}
        challenger = pmap.get(ckey)
        defender = pmap.get(dkey)
        if not challenger or not defender:
            await sb_patch('challenges', f'id=eq.{ch["id"]}', {'status': 'expired'})
            continue
        gain, lose = await apply_forfeit(guild, challenger, defender)
        await sb_patch('challenges', f'id=eq.{ch["id"]}', {'status': 'forfeited'})
        re_c = RANK_EMOJI.get(challenger['rank'], '')
        re_d = RANK_EMOJI.get(defender['rank'], '')
        if log_ch:
            await log_ch.send(
                f'⏰ **Challenge expired!**\n'
                f'**{defender["name"]}** `{defender["rank"]}`{re_d} failed to respond to **{challenger["name"]}**\'s challenge.\n'
                f'🏆 **{challenger["name"]}** **+{gain}pts** · **{defender["name"]}** **−{lose}pts** (forfeit)')
        asyncio.create_task(update_all_posts(guild))

# ── AUTO MEMBER JOIN ──────────────────────────────────────────────────────────
@bot.event
async def on_member_join(member):
    await asyncio.sleep(1)
    key = member.name.lower()
    try:
        existing = await sb_get('players', f'key=eq.{key}')
        if existing:
            print(f'[on_member_join] {member.name} already in DB, skipping.')
            return
        join_order = await get_next_join_order()
        discord_role = get_player_discord_role(member)
        await sb_upsert('players', [{
            'key': key, 'name': member.display_name, 'wins': 0, 'losses': 0,
            'streak': 0, 'rank': 'F', 'points': 0, 'start_points': 0,
            'discord_handle': f'@{member.name}', 'flag': '', 'discord_role': discord_role,
            'join_order': join_order, 'unranked': False,
            'in_tp': False, 'in_rs': False,
            'rs_rank': 'F', 'rs_points': 0, 'rs_wins': 0, 'rs_losses': 0,
            'rs_streak': 0, 'rs_start_points': 0, 'rs_unranked': False,
        }])
        log_ch = bot.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(f'👋 **{member.display_name}** joined the server and was added to the roster. Awaiting league role assignment.')
        print(f'[on_member_join] Added {member.name} to roster (no league assigned).')
    except Exception as e:
        print(f'[on_member_join] ERROR for {member.name}: {e}')

# ── AUTO MEMBER LEAVE ─────────────────────────────────────────────────────────
@bot.event
async def on_member_remove(member):
    # Try current username key first, then fall back to discord_handle match
    # (handles the case where the player changed their username since joining)
    key = member.name.lower()
    handle = f'@{member.name}'
    existing = await sb_get('players', f'key=eq.{key}')
    if not existing:
        existing = await sb_get('players', f'discord_handle=eq.{handle}')
    if not existing:
        print(f'[on_member_remove] {member.name} not found in DB by key or handle — skipping')
        return
    p = existing[0]
    await sb_delete('players', f'key=eq.{p["key"]}')
    asyncio.create_task(update_all_posts(member.guild))
    log_ch = bot.get_channel(LOG_CHANNEL_ID)
    if log_ch: await log_ch.send(f'👋 **{member.display_name}** left the server and was removed from the roster.')

# ── AUTO HANDLE/USERNAME UPDATE ───────────────────────────────────────────────
@bot.event
async def on_user_update(before, after):
    if before.name == after.name: return
    old_handle = f'@{before.name}'
    new_handle  = f'@{after.name}'
    # Find player by old key or old handle
    existing = await sb_get('players', f'key=eq.{before.name.lower()}')
    if not existing:
        existing = await sb_get('players', f'discord_handle=eq.{old_handle}')
    if not existing:
        return
    p = existing[0]
    await sb_patch('players', f'key=eq.{p["key"]}', {'discord_handle': new_handle})
    guild = next(iter(bot.guilds), None)
    log_ch = bot.get_channel(LOG_CHANNEL_ID)
    if log_ch:
        await log_ch.send(f'📝 **{p["name"]}** changed their Discord username: **{before.name}** → **{after.name}** — handle updated automatically.')
    if guild:
        asyncio.create_task(update_all_posts(guild))

# ── AUTO ROLE SYNC ────────────────────────────────────────────────────────────
@bot.event
async def on_member_update(before, after):
    if before.roles == after.roles: return

    # Use IDs — role names may have emojis (e.g. "Ranked Style 🥇")
    before_ids = {r.id for r in before.roles}
    after_ids  = {r.id for r in after.roles}
    added_ids   = after_ids - before_ids
    removed_ids = before_ids - after_ids

    rs_role = find_guild_role(after.guild, RANKED_STYLE_ROLE)
    tp_role = find_guild_role(after.guild, TRUE_POWER_ROLE)

    key = after.name.lower()
    existing = await sb_get('players', f'key=eq.{key}')
    p = existing[0] if existing else None

    elite_role = find_guild_role(after.guild, ELITE_RS_ROLE)

    # ── League join/leave via role assignment ──────────────────────────────────
    if p:
        # Ranked Style role added → join RS
        if rs_role and rs_role.id in added_ids and not p.get('in_rs', False):
            await sb_patch('players', f'key=eq.{key}', {
                'in_rs': True, 'rs_rank': 'F', 'rs_points': 0,
                'rs_wins': 0, 'rs_losses': 0, 'rs_streak': 0, 'rs_start_points': 0,
            })
            await update_discord_rs_role(after.guild, f'@{after.name}', 'F', unranked=False)
            log_ch = bot.get_channel(LOG_CHANNEL_ID)
            if log_ch: await log_ch.send(f'🏅 **{after.display_name}** was given Ranked Style and joined **RS** at **F Rank**!')
            asyncio.create_task(update_all_posts(after.guild))

        # Ranked Style role removed manually — put it back if they're still in RS league.
        # Legitimate removal goes through /leaveleague which sets in_rs=False in DB first,
        # so the re-fetch below will see in_rs=False and skip the re-add.
        elif rs_role and rs_role.id in removed_ids:
            fresh = await sb_get('players', f'key=eq.{key}')
            if fresh and fresh[0].get('in_rs', False):
                print(f'[on_member_update] {after.name}: RS role removed manually → restoring')
                try: await after.add_roles(rs_role)
                except Exception as e: print(f'[on_member_update] failed to restore RS role: {e}')

        # True Power role added → join TP
        if tp_role and tp_role.id in added_ids and not p.get('in_tp', False):
            await sb_patch('players', f'key=eq.{key}', {
                'in_tp': True, 'rank': 'F', 'points': 0,
                'wins': 0, 'losses': 0, 'streak': 0, 'start_points': 0,
            })
            await update_discord_role(after.guild, f'@{after.name}', 'F', p.get('discord_role', ''), unranked=False)
            log_ch = bot.get_channel(LOG_CHANNEL_ID)
            if log_ch: await log_ch.send(f'⚔️ **{after.display_name}** was given True Power and joined **TP** at **F Rank**!')
            asyncio.create_task(update_all_posts(after.guild))

        # True Power role removed manually — put it back if they're still in TP league.
        elif tp_role and tp_role.id in removed_ids:
            fresh = await sb_get('players', f'key=eq.{key}')
            if fresh and fresh[0].get('in_tp', False):
                print(f'[on_member_update] {after.name}: TP role removed manually → restoring')
                try: await after.add_roles(tp_role)
                except Exception as e: print(f'[on_member_update] failed to restore TP role: {e}')

    # ── Elite RS self-assignment guard ─────────────────────────────────────────
    if elite_role and elite_role.id in added_ids:
        if not p or not p.get('is_elite', False):
            print(f'[on_member_update] {after.name}: added Elite RS without qualifying → removing')
            try: await after.remove_roles(elite_role)
            except Exception as e: print(f'[on_member_update] failed to remove Elite RS: {e}')

    # ── Admin role promotion/demotion logging ──────────────────────────────────
    old_discord_role = get_player_discord_role(before)
    new_discord_role = get_player_discord_role(after)
    if new_discord_role != old_discord_role:
        player_name = p['name'] if p else after.display_name
        if p:
            await sb_patch('players', f'key=eq.{key}', {'discord_role': new_discord_role})
            asyncio.create_task(update_all_posts(after.guild))
        await log_role_change(after.guild, player_name, old_discord_role, new_discord_role)

def get_player_discord_role(member):
    # Strip emojis so "High Admin 🌟" matches 'High Admin', etc.
    role_names = {re.sub(r'[^\w\s]', '', r.name).strip() for r in member.roles}
    for role in ['Owner', 'SOD_PVP', 'High Admin', 'Admin Of The Month', 'Admin', 'Manager']:
        if role in role_names: return role
    return ''

async def log_role_change(guild, player_name, old_role, new_role):
    channel = bot.get_channel(ROLE_LOG_ID)
    if not channel:
        try: channel = await bot.fetch_channel(ROLE_LOG_ID)
        except Exception as e: print(f'[role_log] cannot find channel {ROLE_LOG_ID}: {e}'); return
    old_lvl = DISCORD_ROLE_LEVEL.get(old_role, 0)
    new_lvl = DISCORD_ROLE_LEVEL.get(new_role, 0)
    old_display = old_role or 'Member'
    new_display = new_role or 'Member'
    if new_lvl > old_lvl:
        await channel.send(f'⬆️ **{player_name}** was promoted: **{old_display}** → **{new_display}**')
    else:
        await channel.send(f'⬇️ **{player_name}** was demoted: **{old_display}** → **{new_display}**')

# ── SLASH COMMANDS ────────────────────────────────────────────────────────────
async def autocomplete_ranked_players(_interaction: discord.Interaction, current: str):
    try:
        async with httpx.AsyncClient(timeout=2.5) as c:
            r = await c.get(
                f'{SUPABASE_URL}/rest/v1/players?select=name,unranked&order=join_order.asc',
                headers=HEADERS)
            players = r.json() if r.status_code == 200 else []
        return [
            app_commands.Choice(name=p['name'], value=p['name'])
            for p in players
            if not p.get('unranked', False) and current.lower() in p['name'].lower()
        ][:25]
    except Exception as e:
        print(f'[autocomplete] error: {e}')
        return []

@bot.tree.command(name='pvp', description='Log a PvP match result')
@app_commands.describe(winner='Winner name', loser='Loser name', score='Match score', league='Which league')
@app_commands.choices(
    score=[
        app_commands.Choice(name='3 – 0 (Clean Sweep)', value='3-0'),
        app_commands.Choice(name='3 – 1 (Strong Win)',  value='3-1'),
        app_commands.Choice(name='3 – 2 (Close Call)',  value='3-2'),
    ],
    league=[
        app_commands.Choice(name='True Power (TP)', value='TP'),
        app_commands.Choice(name='Ranked Style (RS)', value='RS'),
    ]
)
@app_commands.autocomplete(winner=autocomplete_ranked_players, loser=autocomplete_ranked_players)
async def slash_pvp(interaction: discord.Interaction, winner: str, loser: str, score: app_commands.Choice[str], league: app_commands.Choice[str]):
    await interaction.response.defer()
    if not await check_permission(interaction, 'pvp'): return
    await _log_pvp(interaction, winner, loser, score.value, league.value)

@bot.tree.command(name='addmember', description='Add a new clan member')
@app_commands.describe(name='Player name', rank='Starting rank', flag='Country flag emoji', handle='Discord handle e.g. @joker', role='Server role')
@app_commands.choices(
    rank=[app_commands.Choice(name=r, value=r) for r in RANKS],
    role=[
        app_commands.Choice(name='Member',           value=''),
        app_commands.Choice(name='Manager',          value='Manager'),
        app_commands.Choice(name='Admin Of The Month', value='Admin Of The Month'),
        app_commands.Choice(name='Admin',            value='Admin'),
        app_commands.Choice(name='High Admin',       value='High Admin'),
        app_commands.Choice(name='Owner',            value='Owner'),
    ]
)
async def slash_addmember(interaction: discord.Interaction, name: str, rank: app_commands.Choice[str]=None, flag: str='', handle: str='', role: app_commands.Choice[str]=None):
    await interaction.response.defer()
    if not await check_permission(interaction, 'addmember'): return
    await _add_member(interaction, name, rank.value if rank else 'F', flag, handle, role.value if role else '')

@bot.tree.command(name='removemember', description='Remove a clan member')
@app_commands.describe(name='Player name', kick='True = delete permanently, False = just unrank (default)')
async def slash_removemember(interaction: discord.Interaction, name: str, kick: bool=False):
    await interaction.response.defer()
    if not await check_permission(interaction, 'removemember'): return
    if kick:
        await _remove_member(interaction, name)
    else:
        await _unrank_member(interaction, name)

@bot.tree.command(name='unrank', description='Remove player from leaderboard but keep in roster')
@app_commands.describe(name='Player name', league='Which league')
@app_commands.choices(league=[
    app_commands.Choice(name='True Power (TP)', value='TP'),
    app_commands.Choice(name='Ranked Style (RS)', value='RS'),
    app_commands.Choice(name='Both leagues', value='both'),
])
async def slash_unrank(interaction: discord.Interaction, name: str, league: app_commands.Choice[str]):
    await interaction.response.defer()
    if not await check_permission(interaction, 'unrank'): return
    league_val = league.value
    key = name.lower()
    players = await sb_get('players', f'key=eq.{key}')
    if not players:
        await interaction.followup.send(f'❌ **{name}** not found.'); return
    p = players[0]
    guild = interaction.guild
    if league_val == 'TP' or league_val == 'both':
        if not p.get('in_tp', True):
            if league_val == 'TP':
                await interaction.followup.send(f'ℹ️ **{name}** is not in True Power.'); return
        else:
            await sb_patch('players', f'key=eq.{key}', {'unranked': True})
            if guild and p.get('discord_handle'):
                await update_discord_role(guild, p.get('discord_handle', ''), p.get('rank', 'F'), p.get('discord_role', ''), unranked=True)
    if league_val == 'RS' or league_val == 'both':
        if not p.get('in_rs', False):
            if league_val == 'RS':
                await interaction.followup.send(f'ℹ️ **{name}** is not in Ranked Style.'); return
        else:
            await sb_patch('players', f'key=eq.{key}', {'rs_unranked': True})
            if guild and p.get('discord_handle'):
                # Remove RS rank role but keep Ranked Style base role
                member = await find_member(guild, p.get('discord_handle', ''))
                if member:
                    for rn in RS_ROLE_NAMES.values():
                        r = find_guild_role(guild, rn)
                        if r and r in member.roles:
                            await _add_role_with_retry(member, r, 'remove')
            asyncio.create_task(update_elite(guild))
    if league_val == 'both':
        await interaction.followup.send(f'✅ **{name}** unranked from both leagues.')
    elif league_val == 'TP':
        await interaction.followup.send(f'✅ **{name}** removed from True Power leaderboard (Unranked). Use `/rerank` to restore.')
    else:
        await interaction.followup.send(f'✅ **{name}** removed from Ranked Style leaderboard (RS Unranked).')
    asyncio.create_task(update_all_posts(guild))

@bot.tree.command(name='rerank', description='Re-add an unranked player back to the leaderboard')
@app_commands.describe(name='Player name', league='Which league', rank='New rank to assign (TP only)')
@app_commands.choices(
    league=[
        app_commands.Choice(name='True Power (TP)', value='TP'),
        app_commands.Choice(name='Ranked Style (RS)', value='RS'),
    ],
    rank=[app_commands.Choice(name=r, value=r) for r in RANKS]
)
async def slash_rerank(interaction: discord.Interaction, name: str, league: app_commands.Choice[str], rank: app_commands.Choice[str]=None):
    await interaction.response.defer()
    if not await check_permission(interaction, 'rerank'): return
    key = name.lower()
    players = await sb_get('players', f'key=eq.{key}')
    if not players:
        await interaction.followup.send(f'❌ **{name}** not found.'); return
    p = players[0]
    guild = interaction.guild
    if league.value == 'RS':
        if not p.get('rs_unranked'):
            await interaction.followup.send(f'❌ **{name}** is not RS-unranked.'); return
        await sb_patch('players', f'key=eq.{key}', {'rs_unranked': False})
        if guild:
            await update_discord_rs_role(guild, p.get('discord_handle',''), p.get('rs_rank','F'), unranked=False)
        await interaction.followup.send(f'✅ **{name}** re-added to RS leaderboard at **{p.get("rs_rank","F")} Rank RS**!')
    else:
        if not p.get('unranked'):
            await interaction.followup.send(f'❌ **{name}** is not TP-unranked.'); return
        new_rank = rank.value if rank else p.get('rank', 'F')
        await sb_patch('players', f'key=eq.{key}', {'unranked': False, 'rank': new_rank})
        if guild:
            await update_discord_role(guild, p.get('discord_handle',''), new_rank, p.get('discord_role',''), unranked=False)
        await interaction.followup.send(f'✅ **{name}** re-added to TP leaderboard as **{new_rank} Rank**!')
    asyncio.create_task(update_all_posts(guild))

@bot.tree.command(name='joinleague', description='Join a league at F rank with 0 points')
@app_commands.describe(league='Which league to join')
@app_commands.choices(league=[
    app_commands.Choice(name='True Power (TP)', value='TP'),
    app_commands.Choice(name='Ranked Style (RS)', value='RS'),
])
async def slash_joinleague(interaction: discord.Interaction, league: app_commands.Choice[str]):
    await interaction.response.defer()
    if not await check_permission(interaction, 'joinleague'): return
    username = interaction.user.name.lower()
    all_players = await sb_get('players', 'select=*')
    p = None
    for player in all_players:
        handle = (player.get('discord_handle') or '').lstrip('@').lower()
        if handle == username or player.get('key','').lower() == username:
            p = player; break
    if not p:
        await interaction.followup.send('❌ You are not in the roster. Ask an admin to add you.', ephemeral=True); return
    guild = interaction.guild
    if league.value == 'TP':
        if p.get('in_tp', True):
            await interaction.followup.send('❌ You are already in the True Power league.', ephemeral=True); return
        await sb_patch('players', f'key=eq.{p["key"]}', {'in_tp': True, 'rank': 'F', 'points': 0, 'wins': 0, 'losses': 0, 'streak': 0, 'unranked': False})
        if guild:
            await update_discord_role(guild, p.get('discord_handle',''), 'F', p.get('discord_role',''), unranked=False)
        await interaction.followup.send(f'✅ **{p["name"]}** joined **True Power** at **F Rank**!')
    else:  # RS
        if p.get('in_rs', False):
            await interaction.followup.send('❌ You are already in the Ranked Style league.', ephemeral=True); return
        await sb_patch('players', f'key=eq.{p["key"]}', {'in_rs': True, 'rs_rank': 'F', 'rs_points': 0, 'rs_wins': 0, 'rs_losses': 0, 'rs_streak': 0, 'rs_unranked': False})
        if guild:
            await update_discord_rs_role(guild, p.get('discord_handle',''), 'F', unranked=False)
        await interaction.followup.send(f'✅ **{p["name"]}** joined **Ranked Style** at **F Rank RS**!')
    asyncio.create_task(update_all_posts(guild))

@bot.tree.command(name='leaveleague', description='Leave a league')
@app_commands.describe(league='Which league to leave')
@app_commands.choices(league=[
    app_commands.Choice(name='True Power (TP)', value='TP'),
    app_commands.Choice(name='Ranked Style (RS)', value='RS'),
])
async def slash_leaveleague(interaction: discord.Interaction, league: app_commands.Choice[str]):
    await interaction.response.defer()
    if not await check_permission(interaction, 'leaveleague'): return
    username = interaction.user.name.lower()
    all_players = await sb_get('players', 'select=*')
    p = None
    for player in all_players:
        handle = (player.get('discord_handle') or '').lstrip('@').lower()
        if handle == username or player.get('key','').lower() == username:
            p = player; break
    if not p:
        await interaction.followup.send('❌ You are not in the roster.', ephemeral=True); return
    guild = interaction.guild
    if league.value == 'TP':
        if not p.get('in_tp', True):
            await interaction.followup.send('❌ You are not in the True Power league.', ephemeral=True); return
        await sb_patch('players', f'key=eq.{p["key"]}', {'in_tp': False})
        if guild:
            member = await find_member(guild, p.get('discord_handle',''))
            if member:
                for rn in ROLE_NAMES.values():
                    r = find_guild_role(guild, rn)
                    if r and r in member.roles:
                        await _add_role_with_retry(member, r, 'remove')
        await interaction.followup.send(f'✅ **{p["name"]}** left **True Power**.')
    else:  # RS
        if not p.get('in_rs', False):
            await interaction.followup.send('❌ You are not in the Ranked Style league.', ephemeral=True); return
        await sb_patch('players', f'key=eq.{p["key"]}', {'in_rs': False, 'is_elite': False})
        if guild:
            member = await find_member(guild, p.get('discord_handle',''))
            if member:
                for rn in RS_ROLE_NAMES.values():
                    r = find_guild_role(guild, rn)
                    if r and r in member.roles:
                        await _add_role_with_retry(member, r, 'remove')
                rs_base = find_guild_role(guild, RANKED_STYLE_ROLE)
                if rs_base and rs_base in member.roles:
                    await _add_role_with_retry(member, rs_base, 'remove')
                elite_role = find_guild_role(guild, ELITE_RS_ROLE)
                if elite_role and elite_role in member.roles:
                    await _add_role_with_retry(member, elite_role, 'remove')
        if p.get('is_elite', False):
            asyncio.create_task(update_elite(guild))
        await interaction.followup.send(f'✅ **{p["name"]}** left **Ranked Style**.')
    asyncio.create_task(update_all_posts(guild))

@bot.tree.command(name='ascension', description='RS-only player challenges a TP player to enter True Power')
@app_commands.describe(challenger='RS player name', defender='TP player name', score='Match score')
@app_commands.choices(score=[
    app_commands.Choice(name='3 – 0 (Clean Sweep)', value='3-0'),
    app_commands.Choice(name='3 – 1 (Strong Win)',  value='3-1'),
    app_commands.Choice(name='3 – 2 (Close Call)',  value='3-2'),
])
async def slash_ascension(interaction: discord.Interaction, challenger: str, defender: str, score: app_commands.Choice[str]):
    await interaction.response.defer()
    if not await check_permission(interaction, 'ascension'): return
    all_players = await sb_get('players', 'select=*')
    pmap = {p['key']: p for p in all_players}
    def find_p(raw):
        p = pmap.get(raw.lower())
        if p: return p
        for pl in all_players:
            if pl['name'].lower() == raw.lower(): return pl
        return None
    ch = find_p(challenger)
    df = find_p(defender)
    if not ch: await interaction.followup.send(f'❌ **{challenger}** not found.'); return
    if not df: await interaction.followup.send(f'❌ **{defender}** not found.'); return
    if not ch.get('in_rs', False) or ch.get('in_tp', True):
        await interaction.followup.send(f'❌ **{ch["name"]}** must be RS-only (in RS, not in TP) to use /ascension.'); return
    if not df.get('in_tp', True):
        await interaction.followup.send(f'❌ **{df["name"]}** is not in True Power.'); return
    ch_rs_rank = ch.get('rs_rank', 'F')
    df_tp_rank = df.get('rank', 'F')
    if rank_idx(df_tp_rank) > rs_rank_idx(ch_rs_rank):
        await interaction.followup.send(f'❌ **{df["name"]}** ({df_tp_rank} TP) is higher rank than **{ch["name"]}** ({ch_rs_rank} RS). You can only challenge TP players at your rank or below.'); return

    sc = score.value
    earn = points_win(ch_rs_rank, df_tp_rank, sc)  # use TP formula for entry
    guild = interaction.guild
    dt = datetime.now().strftime('%d.%m.%Y')

    # Entry rank = lower of the two ranks
    entry_rank = RANKS[min(rs_rank_idx(ch_rs_rank), rank_idx(df_tp_rank))]
    entry_points = max(0, df.get('points', 0)) + earn

    lose = points_rs_loss(ch_rs_rank, df_tp_rank)
    df_new_tp_pts = max(0, df.get('points', 0) - lose)

    # Update challenger: enters TP, update RS wins
    await sb_patch('players', f'key=eq.{ch["key"]}', {
        'in_tp': True, 'rank': entry_rank, 'points': entry_points,
        'wins': ch.get('wins', 0) + 1,
        'rs_wins': ch.get('rs_wins', 0) + 1,
        'rs_streak': max(0, ch.get('rs_streak', 0)) + 1,
    })
    # Update defender: loses TP points
    await sb_patch('players', f'key=eq.{df["key"]}', {
        'points': df_new_tp_pts,
        'losses': df.get('losses', 0) + 1,
    })
    # Log as TP match
    await sb_upsert('matches', [{'id': int(datetime.now().timestamp()*1000), 'winner': ch['name'], 'loser': df['name'], 'score': sc, 'date': dt, 'w_rank': entry_rank, 'l_rank': df_tp_rank, 'earn': earn, 'lose': lose, 'league': 'TP'}])
    if guild:
        await update_discord_role(guild, ch.get('discord_handle',''), entry_rank, ch.get('discord_role',''), unranked=False)
    re_e = RANK_EMOJI.get(entry_rank, '')
    await interaction.followup.send(
        f'🌟 **Ascension!**\n'
        f'**{ch["name"]}** `{ch_rs_rank} RS` defeated **{df["name"]}** `{df_tp_rank} TP` **{sc.replace("-"," – ")}**\n'
        f'🎉 **{ch["name"]}** enters **True Power** at **{entry_rank} Rank** {re_e} with **{entry_points} pts**!\n'
        f'**{df["name"]}** **−{lose} TP pts**')
    log_ch = bot.get_channel(LOG_CHANNEL_ID)
    if log_ch:
        await log_ch.send(
            f'🌟 **Ascension match logged!** **{ch["name"]}** ({ch_rs_rank} RS) → **{entry_rank} TP** · defeated **{df["name"]}** ({df_tp_rank} TP) **{sc}**')
    asyncio.create_task(update_all_posts(guild))

@bot.tree.command(name='sync', description='Sync league memberships, roles, and all posts')
async def slash_sync(interaction: discord.Interaction):
    await interaction.response.defer()
    if not await check_permission(interaction, 'sync'): return
    await interaction.followup.send('🔄 Syncing league memberships, roles, and posts…')
    guild = interaction.guild
    await sync_league_from_roles(guild, log_channel=interaction.channel)
    await enforce_roles(guild)
    asyncio.create_task(update_all_posts(guild))

@bot.tree.command(name='leaderboard', description='Refresh leaderboard posts')
async def slash_leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    if not await check_permission(interaction, 'leaderboard'): return
    asyncio.create_task(update_all_posts(interaction.guild))
    await interaction.followup.send('✅ Leaderboard update started!')

@bot.tree.command(name='sethandle', description='Set a player Discord handle')
@app_commands.describe(name='Player name', handle='Discord handle', flag='Country flag emoji')
async def slash_sethandle(interaction: discord.Interaction, name: str, handle: str, flag: str=''):
    await interaction.response.defer()
    if not await check_permission(interaction, 'sethandle'): return
    key = name.lower()
    if not await sb_get('players', f'key=eq.{key}'):
        await interaction.followup.send(f'❌ **{name}** not found.'); return
    data = {'discord_handle': handle}
    if flag: data['flag'] = flag
    await sb_patch('players', f'key=eq.{key}', data)
    await interaction.followup.send(f'✅ Updated **{name}** → {handle} {flag}')
    asyncio.create_task(update_all_posts(interaction.guild))

@bot.tree.command(name='mystats', description='Check your own PvP stats')
async def slash_mystats(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not await check_permission(interaction, 'mystats'): return
    username = interaction.user.name.lower()
    all_players = await sb_get('players', 'select=*')
    p = None
    for player in all_players:
        handle = (player.get('discord_handle') or '').lstrip('@').lower()
        if handle == username:
            p = player; break
    if not p:
        for player in all_players:
            if player.get('key', '').lower() == username:
                p = player; break
    if not p:
        await interaction.followup.send('Could not find you in the roster. Handle not matched.', ephemeral=True)
        return
    t = p['wins'] + p['losses']
    wr = round(p['wins'] / t * 100) if t else 0
    if p['streak'] > 0:
        streak = '+' + str(p['streak']) + ' win streak'
    elif p['streak'] < 0:
        streak = str(abs(p['streak'])) + ' loss streak'
    else:
        streak = 'no streak'
    re = RANK_EMOJI.get(p['rank'], '')
    if p.get('unranked'):
        status = '(Unranked)'
    else:
        status = p['rank'] + ' Rank ' + re
    lines = [
        'Stats for ' + p['name'] + ' ' + (p.get('flag') or ''),
        'Status: ' + status,
        'Record: ' + str(p['wins']) + 'W ' + str(p['losses']) + 'L (' + str(wr) + '% WR)',
        'Points: ' + str(p.get('points', 0)),
        'Streak: ' + streak,
    ]
    await interaction.followup.send(chr(10).join(lines), ephemeral=True)

# ── SHARED LOGIC ──────────────────────────────────────────────────────────────
async def _send(ctx, msg):
    if isinstance(ctx, discord.Interaction): await ctx.followup.send(msg)
    else: await ctx.send(msg)

def _guild(ctx):
    if isinstance(ctx, discord.Interaction): return ctx.guild
    return ctx.guild

async def _log_pvp(ctx, winner, loser, score, league='TP'):
    if score not in ['3-0','3-1','3-2']:
        await _send(ctx,'❌ Score must be 3-0, 3-1, or 3-2'); return
    if winner.lower()==loser.lower():
        await _send(ctx,'❌ Players must be different.'); return
    all_players = await sb_get('players','select=*')
    all_matches = await sb_get('matches','select=winner,loser')
    pmap = {p['key']:p for p in all_players}
    def find_player(raw):
        p = pmap.get(raw.lower())
        if p: return p
        for pl in all_players:
            if pl['name'].lower() == raw.lower():
                return pl
        for pl in all_players:
            if raw.lower().startswith(pl['name'].lower()):
                return pl
        return None
    w = find_player(winner)
    l = find_player(loser)
    if w: winner = w['name']
    if l: loser  = l['name']
    if not w:
        await _send(ctx, f'❌ **{winner}** is not in the roster. Use `/addmember` first.'); return
    if not l:
        await _send(ctx, f'❌ **{loser}** is not in the roster. Use `/addmember` first.'); return
    w['name']=winner; l['name']=loser
    guild=_guild(ctx)
    dt=datetime.now().strftime('%d.%m.%Y')

    if league == 'RS':
        # ── RS branch ────────────────────────────────────────────────────────────
        if not w.get('in_rs', False):
            await _send(ctx, f'❌ **{winner}** is not in the Ranked Style league.'); return
        if not l.get('in_rs', False):
            await _send(ctx, f'❌ **{loser}** is not in the Ranked Style league.'); return
        if w.get('rs_unranked'):
            await _send(ctx, f'❌ **{winner}** is RS-unranked and cannot participate in RS matches.'); return
        if l.get('rs_unranked'):
            await _send(ctx, f'❌ **{loser}** is RS-unranked and cannot participate in RS matches.'); return
        wr = w.get('rs_rank', 'F')
        lr = l.get('rs_rank', 'F')
        earn = points_rs_win(wr, lr, score)
        lose = points_rs_loss(wr, lr)
        w_new_pts = max(0, w.get('rs_points', 0) + earn)
        l_new_pts = max(0, l.get('rs_points', 0) - lose)
        w_new_wins = w.get('rs_wins', 0) + 1
        l_new_losses = l.get('rs_losses', 0) + 1
        w_new_streak = max(0, w.get('rs_streak', 0)) + 1
        l_new_streak = min(0, l.get('rs_streak', 0)) - 1
        # Auto-promote winner (cap at S)
        w_new_rank = wr
        promote_event = ''
        while True:
            ri = rs_rank_idx(w_new_rank)
            if ri >= len(RS_RANKS) - 1: break
            next_rank = RS_RANKS[ri + 1]
            if w_new_pts < RS_THRESH[next_rank]: break
            old_rank = w_new_rank
            w_new_rank = next_rank
            promote_event += f'\n🎉 **{winner}** promoted **{old_rank} → {next_rank}** (RS)!'
        await sb_patch('players', f'key=eq.{w["key"]}', {
            'rs_wins': w_new_wins, 'rs_points': w_new_pts, 'rs_rank': w_new_rank, 'rs_streak': w_new_streak
        })
        await sb_patch('players', f'key=eq.{l["key"]}', {
            'rs_losses': l_new_losses, 'rs_points': l_new_pts, 'rs_streak': l_new_streak
        })
        await sb_upsert('matches',[{'id':int(datetime.now().timestamp()*1000),'winner':winner,'loser':loser,'score':score,'date':dt,'w_rank':w_new_rank,'l_rank':lr,'earn':earn,'lose':lose,'league':'RS'}])
        if guild:
            await update_discord_rs_role(guild, w.get('discord_handle',''), w_new_rank, unranked=w.get('rs_unranked', False))
            await update_discord_rs_role(guild, l.get('discord_handle',''), lr, unranked=l.get('rs_unranked', False))
        result_message = f'✅ **RS Match logged!**\n🏆 **{winner}** `{w_new_rank} RS` **+{earn}pts**  def.  **{loser}** `{lr} RS` **−{lose}pts**\n📊 Score: **{score.replace("-"," – ")}**  ·  {dt}{promote_event}'
        await _send(ctx, result_message)
        asyncio.create_task(update_elite(guild))
        asyncio.create_task(update_all_posts(guild))
    else:
        # ── TP branch (existing behavior) ─────────────────────────────────────
        if not w.get('in_tp', True):
            await _send(ctx, f'❌ **{winner}** is not in the True Power league. They may need to use /ascension to enter TP.'); return
        if not l.get('in_tp', True):
            await _send(ctx, f'❌ **{loser}** is not in the True Power league. They may need to use /ascension.'); return
        if w.get('unranked'):
            await _send(ctx, f'❌ **{winner}** is unranked and cannot participate in ranked matches.'); return
        if l.get('unranked'):
            await _send(ctx, f'❌ **{loser}** is unranked and cannot participate in ranked matches.'); return
        god_event=''
        if w['rank']=='Angel' and l['rank']=='GOD':
            w['rank']='GOD'; l['rank']='Angel'
            god_event=f'\n👑 **{winner} has claimed GOD rank!** 🪐'
        loser_rank_before = l['rank']
        earn=points_win(w['rank'],l['rank'],score)
        lose=points_loss(w['rank'],l['rank'])
        w['wins']=w.get('wins',0)+1; w['streak']=max(0,w.get('streak',0))+1; w['points']=max(0,w.get('points',0)+earn)
        l['losses']=l.get('losses',0)+1; l['streak']=min(0,l.get('streak',0))-1; l['points']=max(0,l.get('points',0)-lose)
        # Auto-promote winner
        promote_event=''
        if not god_event:
            while True:
                ri = rank_idx(w['rank'])
                if ri >= len(RANKS) - 1: break
                next_rank = RANKS[ri + 1]
                if next_rank == 'GOD': break
                if w.get('points', 0) < THRESH[next_rank]: break
                old_rank = w['rank']
                w['rank'] = next_rank
                promote_event += f'\n🎉 **{winner}** promoted **{old_rank} → {next_rank}**!'
        await sb_upsert('players',[w,l])
        await sb_upsert('matches',[{'id':int(datetime.now().timestamp()*1000),'winner':winner,'loser':loser,'score':score,'date':dt,'w_rank':w['rank'],'l_rank':l['rank'],'earn':earn,'lose':lose,'league':'TP'}])
        if guild:
            await update_discord_role(guild,w.get('discord_handle',''),w['rank'],w.get('discord_role',''),unranked=w.get('unranked',False))
            await update_discord_role(guild,l.get('discord_handle',''),l['rank'],l.get('discord_role',''),unranked=l.get('unranked',False))
        re_w=RANK_EMOJI.get(w['rank'],''); re_l=RANK_EMOJI.get(l['rank'],'')
        await _send(ctx,f'✅ **Match logged!**\n🏆 **{winner}** `{w["rank"]}`{re_w} **+{earn}pts**  def.  **{loser}** `{l["rank"]}`{re_l} **−{lose}pts**\n📊 Score: **{score.replace("-"," – ")}**  ·  {dt}{god_event}{promote_event}')
        asyncio.create_task(update_all_posts(guild))

async def _add_member(ctx, name, rank='F', flag='', handle='', role=''):
    if rank not in RANKS:
        await _send(ctx,f'❌ Invalid rank. Options: {", ".join(RANKS)}'); return
    key=name.lower()
    existing = await sb_get('players',f'key=eq.{key}')
    if existing:
        if existing[0].get('unranked'):
            await sb_patch('players',f'key=eq.{key}',{'unranked':False,'rank':rank})
            guild=_guild(ctx)
            if guild and (handle or existing[0].get('discord_handle')):
                h = handle or existing[0].get('discord_handle','')
                await update_discord_role(guild, h, rank, role or existing[0].get('discord_role',''), unranked=False)
            await _send(ctx,f'✅ **{name}** re-added to leaderboard as **{rank} Rank**!')
            asyncio.create_task(update_all_posts(guild))
            return
        await _send(ctx,f'❌ **{name}** already exists.'); return
    jo=await get_next_join_order()
    await sb_upsert('players',[{'key':key,'name':name,'wins':0,'losses':0,'streak':0,'rank':rank,'points':0,'start_points':0,'discord_handle':handle,'flag':flag,'discord_role':role,'join_order':jo,'unranked':False}])
    re=RANK_EMOJI.get(rank,'')
    await _send(ctx,f'✅ **{name}** {flag} added as **{rank} Rank** {re}!')
    guild=_guild(ctx)
    if guild and handle: await update_discord_role(guild,handle,rank,role,unranked=False)
    asyncio.create_task(update_all_posts(guild))

async def _remove_member(ctx, name):
    key=name.lower()
    if not await sb_get('players',f'key=eq.{key}'):
        await _send(ctx,f'❌ **{name}** not found.'); return
    await sb_delete('players',f'key=eq.{key}')
    await _send(ctx,f'✅ **{name}** permanently removed from the clan.')
    asyncio.create_task(update_all_posts(_guild(ctx)))

async def _unrank_member(ctx, name):
    key=name.lower()
    players = await sb_get('players',f'key=eq.{key}')
    if not players:
        await _send(ctx,f'❌ **{name}** not found.'); return
    p = players[0]
    if p.get('unranked'):
        await _send(ctx,f'ℹ️ **{name}** is already unranked.'); return
    await sb_patch('players',f'key=eq.{key}',{'unranked':True})
    guild=_guild(ctx)
    if guild and p.get('discord_handle'):
        await update_discord_role(guild, p.get('discord_handle',''), p.get('rank','F'), p.get('discord_role',''), unranked=True)
    await _send(ctx,f'✅ **{name}** removed from leaderboard (Unranked). Use `/rerank` to restore.')
    asyncio.create_task(update_all_posts(guild))

# ── CHALLENGE SLASH COMMANDS ──────────────────────────────────────────────────
@bot.tree.command(name='challenge', description='Challenge another clan member to a PvP match')
@app_commands.describe(name='The player you want to challenge', league='Which league')
@app_commands.choices(league=[
    app_commands.Choice(name='True Power (TP)', value='TP'),
    app_commands.Choice(name='Ranked Style (RS)', value='RS'),
])
async def slash_challenge(interaction: discord.Interaction, name: str, league: app_commands.Choice[str]):
    await interaction.response.defer()
    if not await check_permission(interaction, 'challenge'): return

    league_val = league.value

    # Find challenger in DB by Discord handle
    username = interaction.user.name.lower()
    all_players = await sb_get('players', 'select=*')
    challenger = None
    for p in all_players:
        handle = (p.get('discord_handle') or '').lstrip('@').lower()
        if handle == username or p.get('key','').lower() == username:
            challenger = p; break
    if not challenger:
        await interaction.followup.send('❌ You are not in the roster.', ephemeral=True); return
    if challenger.get('unranked'):
        await interaction.followup.send('❌ Unranked players cannot issue challenges.', ephemeral=True); return

    # Find defender
    dkey = name.lower()
    defender = next((p for p in all_players if p['key'] == dkey), None)
    if not defender:
        await interaction.followup.send(f'❌ **{name}** not found in roster.'); return
    if defender.get('unranked'):
        await interaction.followup.send(f'❌ **{name}** is unranked and cannot be challenged.'); return
    if challenger['key'] == dkey:
        await interaction.followup.send('❌ You cannot challenge yourself.'); return

    # League membership validation
    if league_val == 'TP':
        if not challenger.get('in_tp', True):
            await interaction.followup.send('❌ You are not in the True Power league.', ephemeral=True); return
        if not defender.get('in_tp', True):
            await interaction.followup.send(f'❌ **{name}** is not in the True Power league.'); return
        crank, drank = challenger['rank'], defender['rank']
    else:  # RS
        if not challenger.get('in_rs', False):
            await interaction.followup.send('❌ You are not in the Ranked Style league.', ephemeral=True); return
        if not defender.get('in_rs', False):
            await interaction.followup.send(f'❌ **{name}** is not in the Ranked Style league.'); return
        crank, drank = challenger.get('rs_rank', 'F'), defender.get('rs_rank', 'F')

    # Rank gap check — GOD can only be challenged by Angel-rank players (TP only)
    if league_val == 'TP':
        gap = rank_idx(drank) - rank_idx(crank)
        if drank == 'GOD':
            angel_role = discord.utils.get(interaction.guild.roles, name='Angel Rank 🪽') if interaction.guild else None
            if not angel_role or angel_role not in interaction.user.roles:
                await interaction.followup.send('❌ Only **Angel** rank players can challenge the **GOD**.'); return
        elif gap > 3:
            await interaction.followup.send(f'❌ **{name}** is too far above your rank. You can only challenge up to **3 ranks** above you.'); return
    else:  # RS
        gap = rs_rank_idx(drank) - rs_rank_idx(crank)
        if gap > 3:
            await interaction.followup.send(f'❌ **{name}** is too far above your RS rank. You can only challenge up to **3 ranks** above you.'); return

    # Check for existing open challenge between them
    existing = await get_open_challenge(challenger['key'], dkey)
    if existing:
        await interaction.followup.send(f'❌ You already have an open challenge against **{name}**.'); return
    # Also check reverse — defender already challenged challenger
    reverse = await get_open_challenge(dkey, challenger['key'])
    if reverse:
        await interaction.followup.send(f'ℹ️ **{name}** has already challenged you! Use `/accept` to accept their challenge instead.'); return

    # Re-challenge check
    allowed, reason = await can_rechallenge(challenger['key'], dkey, crank, drank)
    if not allowed:
        await interaction.followup.send(f'❌ {reason}'); return

    # Also check if challenger already has a pending outgoing challenge
    open_out = await get_pending_as_challenger(challenger['key'])
    if open_out:
        existing_target = open_out[0]['defender_key']
        await interaction.followup.send(f'❌ You already have an open challenge (vs **{existing_target}**). You can only have one open challenge at a time.'); return

    # Create challenge
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=CHALLENGE_EXPIRY_DAYS)
    challenge_id = int(now.timestamp() * 1000)
    await sb_upsert('challenges', [{
        'id': challenge_id,
        'challenger_key': challenger['key'],
        'challenger_name': challenger['name'],
        'defender_key': dkey,
        'defender_name': defender['name'],
        'status': 'pending',
        'created_at': now.isoformat(),
        'expires_at': expires.isoformat(),
        'challenger_rank_at_time': crank,
        'defender_rank_at_time': drank,
        'league': league_val,
    }])

    league_label = f'[{league_val}] ' if league_val else ''
    re_c = RANK_EMOJI.get(crank, '')
    re_d = RANK_EMOJI.get(drank, '')
    defender_mention = fmt_handle(defender.get('discord_handle', ''), interaction.guild) or defender['name']
    log_ch = bot.get_channel(LOG_CHANNEL_ID)
    msg = (f'⚔️ **{league_label}Challenge issued!**\n'
           f'**{challenger["name"]}** `{crank}`{re_c} → {defender_mention} `{drank}`{re_d}\n'
           f'{defender["name"]} has **7 days** to `/accept` or `/decline`. '
           f'No response = forfeit (**−{forfeit_points_loss(crank, drank)}pts**).')
    await interaction.followup.send(msg)
    if log_ch and log_ch.id != interaction.channel_id:
        await log_ch.send(msg)


@bot.tree.command(name='accept', description='Accept a pending challenge against you')
@app_commands.describe(challenger='Name of the player who challenged you')
async def slash_accept(interaction: discord.Interaction, challenger: str):
    await interaction.response.defer()
    if not await check_permission(interaction, 'accept'): return

    username = interaction.user.name.lower()
    all_players = await sb_get('players', 'select=*')
    defender = None
    for p in all_players:
        handle = (p.get('discord_handle') or '').lstrip('@').lower()
        if handle == username or p.get('key','').lower() == username:
            defender = p; break
    if not defender:
        await interaction.followup.send('❌ You are not in the roster.', ephemeral=True); return

    ckey = challenger.lower()
    rows = await sb_get('challenges',
        f'challenger_key=eq.{ckey}&defender_key=eq.{defender["key"]}&status=eq.pending')
    if not rows:
        await interaction.followup.send(f'❌ No pending challenge from **{challenger}** found.'); return

    ch = rows[0]
    await sb_patch('challenges', f'id=eq.{ch["id"]}', {'status': 'accepted'})
    challenger_mention = fmt_handle(
        next((p.get('discord_handle','') for p in all_players if p['key']==ckey), ''),
        interaction.guild) or challenger
    re_c = RANK_EMOJI.get(ch['challenger_rank_at_time'], '')
    re_d = RANK_EMOJI.get(ch['defender_rank_at_time'], '')
    msg = (f'✅ **Challenge accepted!**\n'
           f'{challenger_mention} `{ch["challenger_rank_at_time"]}`{re_c} vs **{defender["name"]}** `{ch["defender_rank_at_time"]}`{re_d}\n'
           f'Play your match and log the result with `/pvp`!')
    await interaction.followup.send(msg)
    log_ch = bot.get_channel(LOG_CHANNEL_ID)
    if log_ch and log_ch.id != interaction.channel_id:
        await log_ch.send(msg)


@bot.tree.command(name='decline', description='Decline a pending challenge against you')
@app_commands.describe(challenger='Name of the player who challenged you')
async def slash_decline(interaction: discord.Interaction, challenger: str):
    await interaction.response.defer()
    if not await check_permission(interaction, 'decline'): return

    username = interaction.user.name.lower()
    all_players = await sb_get('players', 'select=*')
    defender = None
    for p in all_players:
        handle = (p.get('discord_handle') or '').lstrip('@').lower()
        if handle == username or p.get('key','').lower() == username:
            defender = p; break
    if not defender:
        await interaction.followup.send('❌ You are not in the roster.', ephemeral=True); return

    ckey = challenger.lower()
    rows = await sb_get('challenges',
        f'challenger_key=eq.{ckey}&defender_key=eq.{defender["key"]}&status=eq.pending')
    if not rows:
        await interaction.followup.send(f'❌ No pending challenge from **{challenger}** found.'); return

    ch = rows[0]
    players = await sb_get('players', f'key=in.("{ckey}","{defender["key"]}")')
    pmap = {p['key']: p for p in players}
    c_player = pmap.get(ckey)
    d_player = pmap.get(defender['key'])
    if not c_player or not d_player:
        await interaction.followup.send('❌ Could not find player data.'); return

    gain, lose = await apply_forfeit(interaction.guild, c_player, d_player)
    await sb_patch('challenges', f'id=eq.{ch["id"]}', {'status': 'declined'})

    re_d = RANK_EMOJI.get(d_player['rank'], '')
    challenger_mention = fmt_handle(c_player.get('discord_handle',''), interaction.guild) or c_player['name']
    msg = (f'🚫 **Challenge declined!**\n'
           f'**{d_player["name"]}** `{d_player["rank"]}`{re_d} declined {challenger_mention}\'s challenge.\n'
           f'🏆 {challenger_mention} **+{gain}pts** · **{d_player["name"]}** **−{lose}pts** (forfeit penalty)')
    await interaction.followup.send(msg)
    log_ch = bot.get_channel(LOG_CHANNEL_ID)
    if log_ch and log_ch.id != interaction.channel_id:
        await log_ch.send(msg)
    asyncio.create_task(update_all_posts(interaction.guild))


@bot.tree.command(name='challenges', description='View open and recent challenges')
async def slash_challenges(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not await check_permission(interaction, 'challenges'): return

    pending = await sb_get('challenges', 'status=eq.pending&order=created_at.desc')
    recent = await sb_get('challenges', 'status=neq.pending&order=created_at.desc&limit=10')

    lines = ['**Open Challenges**']
    if pending:
        for ch in pending:
            re_c = RANK_EMOJI.get(ch['challenger_rank_at_time'], '')
            re_d = RANK_EMOJI.get(ch['defender_rank_at_time'], '')
            exp = ch['expires_at'][:10]
            league_tag = f'[{ch.get("league", "TP")}] '
            lines.append(f'⚔️ {league_tag}**{ch["challenger_name"]}** `{ch["challenger_rank_at_time"]}`{re_c} → **{ch["defender_name"]}** `{ch["defender_rank_at_time"]}`{re_d} · expires {exp}')
    else:
        lines.append('No open challenges.')

    lines.append('\n**Recent (last 10)**')
    if recent:
        status_emoji = {'accepted':'✅','declined':'🚫','expired':'⏰','forfeited':'⏰','completed':'🏆'}
        for ch in recent:
            e = status_emoji.get(ch['status'], '❓')
            league_tag = f'[{ch.get("league", "TP")}] '
            lines.append(f'{e} {league_tag}**{ch["challenger_name"]}** → **{ch["defender_name"]}** · {ch["status"]}')
    else:
        lines.append('No recent challenges.')

    await interaction.followup.send('\n'.join(lines), ephemeral=True)

bot.run(os.environ['DISCORD_TOKEN'])

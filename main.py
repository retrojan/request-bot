import disnake
from disnake.ext import commands
import aiohttp
import asyncio
import socket
import time
import json
from urllib.parse import urlparse
import logging
from typing import List, Dict
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

intents = disnake.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix='f$',
    intents=intents,
    help_command=None
)

@bot.event
async def on_ready():
    print(f'Bot {bot.user} started!')
    await bot.change_presence(activity=disnake.Game(name="f$help"))

async def get_ip_from_url(url):
    try:
        parsed_url = urlparse(url)
        hostname = parsed_url.netloc or parsed_url.path
        if not hostname:
            return None
        
        if ':' in hostname:
            hostname = hostname.split(':')[0]
        
        loop = asyncio.get_event_loop()
        ip = await loop.run_in_executor(None, socket.gethostbyname, hostname)
        return ip
    except Exception:
        return "N/A"

async def get_geo_info(ip):
    if ip == "N/A" or ip.startswith("Error"):
        return {"country": "N/A", "region": "N/A", "city": "N/A"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://ip-api.com/json/{ip}", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        return {
                            "country": data.get("country", "N/A"),
                            "region": data.get("regionName", "N/A"),
                            "city": data.get("city", "N/A"),
                            "isp": data.get("isp", "N/A"),
                            "org": data.get("org", "N/A")
                        }
    except Exception:
        pass
    
    return {"country": "N/A", "region": "N/A", "city": "N/A", "isp": "N/A", "org": "N/A"}

async def determine_protocol(hostname):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://{hostname}", timeout=3, allow_redirects=True) as response:
                if response.status < 500:
                    return "https"
    except:
        pass
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{hostname}", timeout=3, allow_redirects=True) as response:
                if response.status < 500:
                    return "http"
    except:
        pass
    
    return "https"

async def check_single_site(url, options_set):
    parsed = urlparse(url)
    
    if parsed.scheme:
        protocol = parsed.scheme
        hostname = parsed.netloc
        url_to_check = url
    else:
        hostname = url.split('/')[0]
        protocol = await determine_protocol(hostname)
        url_to_check = f"{protocol}://{url}"
    
    result = {
        'full_url': url_to_check,
        'protocol': protocol,
        'status': 'N/A',
        'code': 'N/A',
        'ping': 'N/A',
        'ip': 'N/A',
        'country': 'N/A',
        'region': 'N/A',
        'city': 'N/A',
        'isp': 'N/A',
        'org': 'N/A'
    }
    
    try:
        if 'ip' in options_set:
            ip = await get_ip_from_url(url_to_check)
            result['ip'] = ip
            
            if 'geo' in options_set and ip != "N/A":
                geo_info = await get_geo_info(ip)
                result.update(geo_info)
        
        if 'p' in options_set or 'ping' in options_set:
            host = hostname.split(':')[0]
            port = 443 if protocol == "https" else 80
            try:
                start_time = time.time()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=3
                )
                end_time = time.time()
                writer.close()
                await writer.wait_closed()
                result['ping'] = round((end_time - start_time) * 1000, 2)
            except:
                result['ping'] = "N/A"
        
        if 's' in options_set or 'status' in options_set or 'c' in options_set or 'code' in options_set:
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url_to_check, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        result['code'] = response.status
                        result['status'] = 'Online' if response.status < 400 else 'Error'
                except aiohttp.ClientError:
                    result['status'] = 'Offline'
                    
    except Exception:
        pass
    
    return result

class PaginatorView(disnake.ui.View):
    
    def __init__(self, embeds: List[disnake.Embed], timeout: float = 120):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0
        self.update_buttons()
    
    def update_buttons(self):
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.embeds) - 1
    
    @disnake.ui.button(label="◀️", style=disnake.ButtonStyle.grey)
    async def previous_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    @disnake.ui.button(label="▶️", style=disnake.ButtonStyle.grey)
    async def next_button(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)
    
    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        await self.message.edit(view=self)

def create_embeds(results: List[Dict], options_set: set, urls: List[str]):
    embeds = []
    sites_per_page = 5
    
    unique_urls = []
    unique_results = []
    seen = set()
    
    for url, result in zip(urls, results):
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
            unique_results.append(result)
    
    for page in range(0, len(unique_results), sites_per_page):
        page_results = unique_results[page:page + sites_per_page]
        page_urls = unique_urls[page:page + sites_per_page]
        page_num = page // sites_per_page + 1
        total_pages = (len(unique_results) - 1) // sites_per_page + 1
        
        embed = disnake.Embed(
            title=f"Check Results ({page_num}/{total_pages})",
            color=disnake.Color.dark_green()
        )
        
        for result in page_results:
            site_info = []
            
            if 's' in options_set or 'status' in options_set:
                if result['status'] != 'N/A':
                    site_info.append(f"Status: {result['status']}")
            
            if 'c' in options_set or 'code' in options_set:
                if result['code'] != 'N/A':
                    site_info.append(f"Code: {result['code']}")
            
            if 'p' in options_set or 'ping' in options_set:
                if result['ping'] != 'N/A':
                    ping_text = f"{result['ping']}ms" if isinstance(result['ping'], (int, float)) else str(result['ping'])
                    site_info.append(f"Ping: {ping_text}")
            
            if 'ip' in options_set:
                site_info.append(f"IP: {result['ip']}")
            
            if 'geo' in options_set:
                geo_parts = []
                if result['country'] != 'N/A':
                    geo_parts.append(result['country'])
                if result['city'] != 'N/A' and result['city'] not in geo_parts:
                    geo_parts.append(result['city'])
                if geo_parts:
                    site_info.append(f"Location: {', '.join(geo_parts)}")
            
            if site_info:
                embed.add_field(
                    name=result['full_url'],
                    value="\n".join(site_info),
                    inline=False
                )
        
        if not embed.fields:
            embed.description = "No data to display."
        embeds.append(embed)
    
    return embeds

@bot.command(name='r', aliases=['request'])
async def request_info(ctx, *args):
    async with ctx.typing():
        
        if not args:
            embed = disnake.Embed(
                title="Error",
                description="Usage: f$r <url1> <url2> ... [options]\nExample: f$r steampowered.com -s -c -p",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        urls = []
        options = set()
        
        for arg in args:
            if arg.startswith('-'):
                opt = arg.lstrip('-')
                if opt in ['s', 'status', 'c', 'code', 'p', 'ping', 'ip', 'geo']:
                    if opt == 's': options.add('status')
                    elif opt == 'c': options.add('code')
                    elif opt == 'p': options.add('ping')
                    elif opt == 'geo': options.add('geo')
                    else: options.add(opt)
            else:
                urls.append(arg)
        
        if not urls:
            embed = disnake.Embed(
                title="Error",
                description="Specify at least one URL. Example: f$r steampowered.com -s",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        if not options:
            embed = disnake.Embed(
                title="Error",
                description="Specify at least one option. Example: f$r steampowered.com -s\nAvailable options: -s, -c, -p, -ip, -geo",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        try:
            tasks = [check_single_site(url, options) for url in urls]
            results = await asyncio.gather(*tasks)
            
            embeds = create_embeds(results, options, urls)
            
            if embeds:
                view = PaginatorView(embeds)
                await ctx.send(embed=embeds[0], view=view)
            else:
                await ctx.send("Could not get information about the sites.")
                
        except Exception as e:
            embed = disnake.Embed(
                title="Error",
                description=f"Error checking sites:\n{str(e)[:500]}",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)

@bot.command(name='h', aliases=['help'])
async def help_command(ctx):
    embed = disnake.Embed(
        title="Commands Help",
        description="Bot for checking website information",
        color=disnake.Color.dark_green()
    )
    
    embed.add_field(
        name="Main command",
        value="f$r <url1> <url2> ... [options]",
        inline=False
    )
    
    embed.add_field(
        name="Options (specify at least one)",
        value="""
-s / -status - Show site status
-c / -code - Show status code
-p / -ping - Show ping
-ip - Show server IP address
-geo - Show geolocation""",
        inline=False
    )
    embed.add_field(
        name="Examples",
        value="""
f$r steampowered.com -s -c
f$r google.com github.com -p -ip
f$r example.com -status -code -ping -ip -geo
f$r site1.com site2.com site3.com -s -c""",
        inline=False
    )
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        embed = disnake.Embed(
            title="Error",
            description="Usage: f$r <url1> <url2> ... [options]\nExample: f$r steampowered.com -s -c -p",
            color=disnake.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        embed = disnake.Embed(
            title="Error",
            description=str(error)[:500],
            color=disnake.Color.red()
        )
        await ctx.send(embed=embed)

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass
def start_health_server():
    try:
        server = HTTPServer(('0.0.0.0', 8000), HealthHandler)
        print(f"Server started on port 8000")
        server.serve_forever()
    except Exception as e:
        print(f"Server error: {e}")
health_thread = threading.Thread(target=start_health_server, daemon=True)
health_thread.start()
print("Health check ready on port 8000")



load_dotenv()
if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    bot.run(TOKEN)


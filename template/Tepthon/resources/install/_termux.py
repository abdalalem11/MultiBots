from datetime import datetime
from os import path, system
from time import sleep

try:
    from colorama import Back, Fore, Style
except ModuleNotFoundError:
    print("Installing colorama...")
    system("pip install -q colorama")
    from colorama import Back, Fore, Style


def clear():
    system("clear")


MANDATORY_REQS = [
    "telethon",
    "gitpython",
    "telegraph",
    "requests",
    "pillow",
    "python-decouple",
    "youtube-search-python",
    "yt-dlp",
    "tabulate",
]
APT_PACKAGES = ["ffmpeg", "neofetch", "mediainfo"]
COPYRIGHT = f"Tepthon {datetime.now().year}"
HEADER = f"""
    T
    E
    P
    T
    H
    O
    N
"""

def with_header(text):
    return Fore.MAGENTA + HEADER + Fore.RESET + "\n\n" + text


def ask_process_apt_install():
    strm = input("").lower().strip()
    if strm == "e":
        print("Exiting...")
        exit(0)
    elif strm == "a":
        names = " ".join(APT_PACKAGES)
        print("Installing all apt-packages...")
        system(f"apt install {names} -y")
    elif strm != "s":
        print("Invalid input. Please try again.")
        ask_process_apt_install()


def ask_make_env():
    strm = input("").strip().lower()
    if strm in ["yes", "y"]:
        print(f"{Fore.YELLOW}* Creating .env file..")
        with open(".env", "a") as file:
            for var in ["API_ID", "API_HASH", "SESSION", "BOT_TOKEN", "REDIS_URI", "REDIS_PASSWORD"]:
                inp = input(f"Enter {var}\n- ")
                file.write(f"{var}={inp}\n")
        print("* Created '.env' file successfully ")

    else:
        print("Skipping .env file creation.")



clear()

print(
    f"""
{Fore.GREEN}- Please review the terms and conditions for installation at the following link

يرجى قراءة شروط وأحكام التنصيب عبر الرابط التالي

https://t.me/TepthonLink/9
. {Fore.RESET}
"""
)

print(with_header("Installing required packages..."))
system(f"pip install -q {' '.join(MANDATORY_REQS)}")

clear()
print(
    with_header(
        f"\n{Fore.GREEN}# Proceeding with APT package installation{Fore.RESET}\n\n"
    )
)
print("Choose an option:")
print(" - A = Install all APT packages")
print(" - S = Skip APT installation")
print(" - E = Exit\n")
ask_process_apt_install()

clear()

print(f"\n{Fore.RED}# Extra Features...\n")
inp = input(f"{Fore.YELLOW}* Do you want colored logs? [Y/N]: ").strip().lower()
if inp in ["yes", "y"]:
    print(f"{Fore.GREEN}Installing coloredlogs...")
    system("pip install -q coloredlogs")
else:
    print("Colored logs skipped.")

clear()

if not path.exists(".env"):
    print(with_header("Proceed to create .env file? [y/N] "))
    ask_make_env()

clear()
print(with_header(f"\n{Fore.GREEN}Installation complete! 🥳"))
sleep(0.2)
print(f"Use 'cd thetep && python3 -m Tepthon' to run Tepthon.{Fore.RESET}")
sleep(0.5)
print("\nFor help, join @Teptbon_Support.")
sleep(0.5)
print("\nMade by @Tepthon.")

system("pip uninstall -q colorama -y")


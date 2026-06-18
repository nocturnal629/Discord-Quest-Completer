# Discord Quest Completer

A Windows utility that simulates running a game long enough to complete Discord quests — without actually playing anything. It temporarily swaps the real game executable for a lightweight dummy, lets it run for the required time, then restores everything automatically.

---

## Requirements

- Windows 10 or 11
- Steam installed (recommended — required for auto-detection)

---

## How to download

The source files in this repo are for transparency and review. To run the program, grab the `.exe` from the [latest release](../../releases/latest).

---

## How to use

### Basic usage — auto-detect by game name

Type the game name into the **Game Name** field, leave **Address** blank, set a **Duration** (or leave it blank for the default of 15 min), and click **Launch**. The program queries the Steam API to find the game's install path automatically.

> Math expressions work in the Duration field — e.g. `15*2` for 30 minutes, or `7.5` for 7 minutes and 30 seconds.

### Manual address — when auto-detect gets it wrong

In some cases the path returned by the Steam API points to a launcher rather than the actual game executable. If Discord isn't picking up the quest progress, you'll need to find the correct path manually — the [r/DiscordQuests](https://www.reddit.com/r/DiscordQuests/) subreddit or SteamDB depot pages are good sources for this.

Once you have the correct path, paste it into the **Address** field. Two formats are accepted:

- **Relative** (inside `steamapps\common`): `Valorant\VALORANT.exe`
- **Full absolute path**: `C:\Riot Games\VALORANT\live\VALORANT.exe`

You can also use the **Browse** button to navigate to the file directly. If the file is inside `steamapps\common` it will be stored as a relative path automatically; otherwise the full path is used.

When an address is provided, the Game Name field is ignored.

### Non-Steam games

For games not on Steam (Riot, Epic, Battle.net, etc.), auto-detection will not work. Use the **Address** field with the full absolute path to the game's executable. The tool will create a fake executable at that exact location, run it for the specified duration, then restore everything automatically — no installation required.

### Note

Some games are not detected by Discord even when run from the correct path. This appears to happen because Discord checks whether the game's folder was created by Steam. If none of the methods above are working and the quest percentage is not going up, try this:

1. Make sure no dummy game window is running.
2. Start downloading the game on Steam and immediately pause it at 1–2%.
3. Launch the quest completer as usual.

If the dummy window was accidentally left open when you started the download, close it, unpause the Steam download for another percent, pause it again, and then run the quest completer.

---

## What happens under the hood

- If the game is already installed, the original `.exe` is renamed to `old_game_file.exe` before the dummy takes its place, and restored automatically once the timer ends.
- If the game is not installed, a temporary directory path is created for the duration and deleted when the timer finishes.
- The restore step runs inside a `finally` block, so the original executable is recovered even if something goes wrong mid-run.

---

## Disclaimer & limitation of liability

**This tool is provided for educational and research purposes only.**

By downloading or running this software you agree to the following:

- **No affiliation.** This project is not affiliated with, endorsed by, or supported by Discord, any game developer, or their parent companies.
- **Risk of use.** Automating quest completion may violate Discord's Terms of Service. Use of this program may result in account warnings, suspensions, or permanent bans.
- **No warranty.** This software is provided "as is," without any warranty of any kind. No guarantees are made regarding safety, functionality, or continued compatibility.
- **Limitation of liability.** The author(s) are not liable for any claims, damages, account losses, or other consequences arising from the use or misuse of this software.
- **User responsibility.** You are solely responsible for your actions and any consequences that follow from running this program.

**If you do not agree to these terms, do not download or run this software.**

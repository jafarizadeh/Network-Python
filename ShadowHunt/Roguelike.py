import curses
import math

# Game map: '#' = wall, '.' = floor, '$' = target
game_map = [
    "####################",
    "#..............#####",
    "#..######..........#",
    "#..#....#..........#",
    "#..#....######..####",
    "#..............#..$#",
    "#######..........#.#",
    "#.................##",
    "####################"
]

# Position of the goal ($)
goal_x = 18
goal_y = 5

def main(stdscr):
    curses.curs_set(0)        # Hide cursor
    stdscr.nodelay(False)     # Wait for user input
    stdscr.keypad(True)       # Enable arrow keys

    player_x = 1
    player_y = 1

    while True:
        stdscr.clear()

        # Draw the map
        for y, row in enumerate(game_map):
            stdscr.addstr(y, 0, row)

        # Draw the player
        stdscr.addstr(player_y, player_x, "@")

        # Calculate distance to goal
        dx = goal_x - player_x
        dy = goal_y - player_y
        distance = math.sqrt(dx*dx + dy*dy)

        # Show win message if within 3 units
        if distance <= 3:
            stdscr.addstr(len(game_map), 0, "You Win!")

        stdscr.refresh()

        key = stdscr.getch()
        new_x, new_y = player_x, player_y

        if key == curses.KEY_UP:
            new_y -= 1
        elif key == curses.KEY_DOWN:
            new_y += 1
        elif key == curses.KEY_LEFT:
            new_x -= 1
        elif key == curses.KEY_RIGHT:
            new_x += 1
        elif key == ord("q"):
            break

        # Move only if not a wall
        if game_map[new_y][new_x] != "#":
            player_x, player_y = new_x, new_y

curses.wrapper(main)

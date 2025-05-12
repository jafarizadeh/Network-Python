import curses
import socket
import json
import threading
import math
import time

MAP = [
    "####################",
    "#................###",
    "#..######..........#",
    "#..#....#..........#",
    "#..#....######..####",
    "#..............#...#",
    "#######..........#.#",
    "#.................##",
    "####################"
]

other_player = {'x': None, 'y': None}

def receive_data(sock):
    global other_player
    while True:
        try:
            data = sock.recv(1024).decode()
            info = json.loads(data)
            other_player = info['other']
        except:
            break

def main(stdscr):
    global other_player
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)

    player_x, player_y = 1, 1

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", 12345))

    # Start background thread
    threading.Thread(target=receive_data, args=(sock,), daemon=True).start()

    while True:
        stdscr.clear()

        for y, row in enumerate(MAP):
            stdscr.addstr(y, 0, row)

        stdscr.addstr(player_y, player_x, 'A')

        # Send position
        msg = json.dumps({'player': 'A', 'x': player_x, 'y': player_y})
        sock.send(msg.encode())

        # Show win message if close
        ox, oy = other_player.get('x'), other_player.get('y')
        if ox is not None and oy is not None:
            dist = math.hypot(player_x - ox, player_y - oy)
            if dist <= 3:
                stdscr.addstr(len(MAP), 0, "You found them!")

        stdscr.refresh()

        try:
            key = stdscr.getch()
        except:
            key = -1

        new_x, new_y = player_x, player_y
        if key == curses.KEY_UP: new_y -= 1
        elif key == curses.KEY_DOWN: new_y += 1
        elif key == curses.KEY_LEFT: new_x -= 1
        elif key == curses.KEY_RIGHT: new_x += 1
        elif key == ord("q"): break

        if 0 <= new_y < len(MAP) and 0 <= new_x < len(MAP[0]) and MAP[new_y][new_x] != "#":
            player_x, player_y = new_x, new_y

        time.sleep(0.05)

    sock.close()

curses.wrapper(main)

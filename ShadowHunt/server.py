import socket
import threading
import json

players = {
    'A': {'x': 1, 'y': 1},
    'B': {'x': 18, 'y': 5}
}

def handle_client(conn, player_id):
    global players
    while True:
        try:
            data = conn.recv(1024).decode()
            if not data:
                break
            info = json.loads(data)
            players[player_id] = {'x': info['x'], 'y': info['y']}
            # Prepare data to send back
            other_id = 'B' if player_id == 'A' else 'A'
            response = {
                'self': players[player_id],
                'other': players[other_id],
            }
            conn.send(json.dumps(response).encode())
        except:
            break
    conn.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', 12345))
    server.listen(2)
    print("Server listening on port 12345")

    for player_id in ['A', 'B']:
        conn, addr = server.accept()
        print(f"Player {player_id} connected from {addr}")
        threading.Thread(target=handle_client, args=(conn, player_id)).start()

if __name__ == "__main__":
    main()

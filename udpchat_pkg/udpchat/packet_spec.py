# udpchat/packet_spec.py
"""
Defines required fields for each supported packet type.
This central schema allows the server (and potentially client)
to validate incoming data before processing.

Benefits:
- Consistent packet format across client and server
- Easier to modify protocol (single source of truth)
- Protects against malformed or incomplete messages
"""

# --- Required field sets for each packet type ------------------------------

# Sent when a new user joins the lobby
JOIN_FIELDS = {"type", "name"}

# Sent by clients in the public lobby
PUBLIC_MSG_FIELDS = {"type", "name", "text"}

# Sent when a client exits gracefully
QUIT_FIELDS = {"type", "name"}

# Sent when a user creates a new private room
CREATE_ROOM_FIELDS = {"type", "name", "room"}

# Sent to invite another user into a room
INVITE_FIELDS = {"type", "room", "from", "to"}

# Sent by a user to accept an invite
ACCEPT_INV_FIELDS = {"type", "name", "room"}

# Message sent within a private room
ROOM_MSG_FIELDS = {"type", "room", "from", "text"}

# Sent by the server to notify clients (info or error)
SYSTEM_MSG_FIELDS = {"type", "text"}

# --- Master mapping: packet type string ➔ required field set -----------

EXPECTED_FIELDS_BY_TYPE = {
    "join": JOIN_FIELDS,
    "msg": PUBLIC_MSG_FIELDS,
    "quit": QUIT_FIELDS,
    "create_room": CREATE_ROOM_FIELDS,
    "invite": INVITE_FIELDS,
    "accept_invite": ACCEPT_INV_FIELDS,
    "room_msg": ROOM_MSG_FIELDS,
    "sys": SYSTEM_MSG_FIELDS,
}

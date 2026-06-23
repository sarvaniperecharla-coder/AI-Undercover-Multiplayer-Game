import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import random
import requests

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet"
)
def generate_ai_word_pair():

    prompt = """
Generate one pair of easy related words.

Categories:
- Animals
- Food
- Fruits
- Vehicles
- Sports
- School items
- Household objects

Rules:
- Very common words
- One word only
- No difficult vocabulary

Return exactly:

Teacher: word
Student: word

Example:

Teacher: Pen
Student: Pencil

Do not add explanations.
Do not add extra text.
"""
    response = requests.post(
        "http://127.0.0.1:11434/api/generate",
        json={
            "model": "llama3.2",
            "prompt": prompt,
            "stream": False
        }
    )

    text = response.json()["response"]

    print("RAW AI RESPONSE:")
    print(text)

    civilian_word = None
    undercover_word = None

    for line in text.splitlines():

        if line.startswith("Teacher:"):

            civilian_word = (
                line.replace("Teacher:", "")
                .strip()
            )

        elif line.startswith("Student:"):

            undercover_word = (
                line.replace("Student:", "")
                .strip()
            )

    if civilian_word and undercover_word:

        return (
            civilian_word,
            undercover_word
        )

    raise Exception(
        "Could not parse AI response"
    )

    

rooms = {}

WORD_PAIRS = [
    ("Cat", "Dog"),
    ("Tea", "Coffee"),
    ("Apple", "Orange"),
    ("Car", "Bike"),
    ("Beach", "Desert")
]


@app.route("/")
def home():
    return render_template("index.html")


@socketio.on("create_room")
def create_room(data):

    print("CREATE ROOM CLICKED")

    name = data["name"].strip()

    room_id = str(random.randint(1000, 9999))

    while room_id in rooms:
        room_id = str(random.randint(1000, 9999))

    player = {
        "sid": request.sid,
        "name": name
    }

    rooms[room_id] = {
        "host": request.sid,
        "players": [player],
        "game_started": False,
        "votes": {},
        "clues": [],
        "round": 1, 
        "undercover_sid": None,
        "eliminated_players": [],
        "clue_order": [],
        "current_turn": 0,
        
    }

    join_room(room_id)

    emit("room_created", {
        "room_id": room_id,
        "players": rooms[room_id]["players"]
    })


@socketio.on("join_room")
def join_game(data):

    room_id = data["room_id"]
    name = data["name"].strip()

    if room_id not in rooms:
        emit("error_message", "Room not found")
        return

    if rooms[room_id]["game_started"]:
        emit("error_message", "Game already started")
        return

    player = {
        "sid": request.sid,
        "name": name
    }

    rooms[room_id]["players"].append(player)

    join_room(room_id)

    socketio.emit(
        "room_update",
        rooms[room_id]["players"],
        room=room_id
    )
@socketio.on("start_game")
def start_game(data):

    room_id = data["room_id"]

    if room_id not in rooms:
        return

    if request.sid != rooms[room_id]["host"]:

        emit(
            "error_message",
            "Only the room creator can start the game"
        )

        return

    players = rooms[room_id]["players"]

    if len(players) < 3:

        emit(
            "error_message",
            "Need at least 3 players"
        )

        return

    rooms[room_id]["game_started"] = True
    rooms[room_id]["votes"] = {}
    rooms[room_id]["clues"] = []

    try:

       civilian_word, undercover_word = (
        generate_ai_word_pair()
    )

       print(
        "AI Words:",
        civilian_word,
        undercover_word
    )

    except Exception as e:

       print(
        "AI Error:",
        e
    )

       civilian_word, undercover_word = random.choice(
        WORD_PAIRS
    )

    rooms[room_id]["civilian_word"] = civilian_word
    rooms[room_id]["undercover_word"] = undercover_word
    print(
    "Stored words:",
    rooms[room_id]["civilian_word"],
    rooms[room_id]["undercover_word"]
)

    undercover_player = random.choice(
    players
)

    rooms[room_id]["undercover_sid"] = \
    undercover_player["sid"]

    rooms[room_id]["mr_white_sid"] = None
    mr_white_player = None

    if len(players) >= 4:

     available_players = [

        p for p in players

        if p["sid"] !=
        undercover_player["sid"]

    ]
    mr_white_player = random.choice(
            available_players
        )

    rooms[room_id]["mr_white_sid"] = \
            mr_white_player["sid"]
    rooms[room_id]["undercover_alive"] = True

    rooms[room_id]["mr_white_alive"] = (
    mr_white_player is not None
)

    # ------------------------
    # CREATE CLUE ORDER
    # ------------------------

    players_for_order = players.copy()

    random.shuffle(
    players_for_order
)

    if mr_white_player:

     while (
        players_for_order[0]["sid"]
        ==
        mr_white_player["sid"]
    ):

        random.shuffle(
            players_for_order
        )

    rooms[room_id]["clue_order"] = [

    p["sid"]

    for p in players_for_order

]

    rooms[room_id]["current_turn"] = 0

    # ------------------------
    # SEND ROLES
    # ------------------------

    for player in players:

        role = "Civilian"
        word = civilian_word

        if (
            player["sid"]
            ==
            undercover_player["sid"]
        ):

            role = "Undercover"
            word = undercover_word

        elif (

            mr_white_player

            and

            player["sid"]
            ==
            mr_white_player["sid"]

        ):

            role = "Mr. White"
            word = "No Word"

        emit(
            "game_started",
            {
                "role": role,
                "word": word
            },
            to=player["sid"]
        )

    # ------------------------
    # START FIRST TURN
    # ------------------------

    if len(
        rooms[room_id]["clue_order"]
    ) > 0:

        first_sid = \
            rooms[room_id][
                "clue_order"
            ][0]

        socketio.emit(
            "your_turn",
            to=first_sid
        )

    updated_players = []

    for player in rooms[room_id]["players"]:

     updated_players.append({

        "name": player["name"],

        "eliminated":
            player["sid"] in
            rooms[room_id]["eliminated_players"]

    })

     socketio.emit(
    "room_update",
    updated_players,
    room=room_id
)

@socketio.on("submit_clue")
def submit_clue(data):

    room_id = data["room_id"]

    if room_id not in rooms:
        return

    if (
        request.sid
        in
        rooms[room_id]["eliminated_players"]
    ):

        emit(
            "error_message",
            "You are eliminated and cannot submit clues"
        )

        return

    current_sid = (
        rooms[room_id]["clue_order"][
            rooms[room_id]["current_turn"]
        ]
    )

    if request.sid != current_sid:

        emit(
            "error_message",
            "Wait for your turn"
        )

        return

    clue = data["clue"]

    player_name = ""

    for player in rooms[room_id]["players"]:

        if player["sid"] == request.sid:

            player_name = player["name"]

            break

    rooms[room_id]["clues"].append(
        {
            "player": player_name,
            "clue": clue
        }
    )

    socketio.emit(
        "new_clue",
        {
            "player": player_name,
            "clue": clue
        },
        room=room_id
    )

    # Move to next player
    rooms[room_id]["current_turn"] += 1

    if (
        rooms[room_id]["current_turn"]
        <
        len(
            rooms[room_id]["clue_order"]
        )
    ):

        next_sid = (
            rooms[room_id]["clue_order"][
                rooms[room_id]["current_turn"]
            ]
        )

        socketio.emit(
            "your_turn",
            to=next_sid
        )

    else:

        socketio.emit(
            "discussion_started",
            room=room_id
        )
@socketio.on("vote")
def vote_player(data):

    room_id = data["room_id"]

    if room_id not in rooms:
        return

    if request.sid in rooms[room_id]["eliminated_players"]:

        emit(
            "error_message",
            "Eliminated players cannot vote"
        )

        return

    voted_name = data["player"]

    rooms[room_id]["votes"][request.sid] = voted_name

    total_players = len([

        p

        for p in rooms[room_id]["players"]

        if p["sid"] not in rooms[room_id]["eliminated_players"]

    ])

    if len(rooms[room_id]["votes"]) != total_players:
        return

    count = {}

    for vote in rooms[room_id]["votes"].values():

        count[vote] = count.get(vote, 0) + 1

    highest_votes = max(
        count.values()
    )

    tied_players = [

        player

        for player, votes in count.items()

        if votes == highest_votes

    ]

    if len(tied_players) > 1:

        rooms[room_id]["votes"] = {}

        socketio.emit(
            "tie_vote",
            {
                "players": tied_players
            },
            room=room_id
        )

        return

    eliminated = tied_players[0]

    for player in rooms[room_id]["players"]:

        if player["name"] == eliminated:

            rooms[room_id]["eliminated_players"].append(
                player["sid"]
            )

            print(
                "Eliminated players:",
                rooms[room_id]["eliminated_players"]
            )

            break

    socketio.emit(
        "player_eliminated",
        eliminated,
        room=room_id
    )

    active_players = []

    for player in rooms[room_id]["players"]:

        if (
            player["sid"]
            not in rooms[room_id]["eliminated_players"]
        ):

            active_players.append(
                {
                    "name": player["name"],
                    "eliminated": False
                }
            )

    socketio.emit(
        "room_update",
        active_players,
        room=room_id
    )

    is_undercover = False
    is_mr_white = False

    for player in rooms[room_id]["players"]:

        if (
            player["name"] == eliminated
            and
            player["sid"] ==
            rooms[room_id]["undercover_sid"]
        ):
            is_undercover = True

        if (
            rooms[room_id].get("mr_white_sid")
            and
            player["name"] == eliminated
            and
            player["sid"] ==
            rooms[room_id]["mr_white_sid"]
        ):
            is_mr_white = True

    if is_undercover:

        rooms[room_id]["undercover_alive"] = False

        socketio.emit(
            "result",
            f"{eliminated} was the Undercover!",
            room=room_id
        )

    elif is_mr_white:

        rooms[room_id]["mr_white_alive"] = False

        socketio.emit(
            "result",
            f"{eliminated} was Mr. White and is guessing the word!",
            room=room_id
        )

        socketio.emit(
            "mr_white_guess",
            to=rooms[room_id]["mr_white_sid"]
        )

        rooms[room_id]["votes"] = {}

        return

    if (
        not rooms[room_id]["undercover_alive"]
        and
        not rooms[room_id]["mr_white_alive"]
    ):

        socketio.emit(
            "winner",
            "Civilians Win!",
            room=room_id
        )

        return

    rooms[room_id]["votes"] = {}

    
@socketio.on("send_message")
def send_message(data):

    room_id = data["room_id"]
    message = data["message"]

    if room_id not in rooms:
        return

    player_name = ""

    for player in rooms[room_id]["players"]:
        if player["sid"] == request.sid:
            player_name = player["name"]

    socketio.emit(
        "new_message",
        {
            "player": player_name,
            "message": message
        },
        room=room_id
    )

@socketio.on("disconnect")
def disconnect():

    for room_id in list(rooms.keys()):

        rooms[room_id]["players"] = [
            p for p in rooms[room_id]["players"]
            if p["sid"] != request.sid
        ]

        active_players = []

        for player in rooms[room_id]["players"]:

            if (
                player["sid"]
                not in rooms[room_id]["eliminated_players"]
            ):

                active_players.append(player)

        print(
            "ACTIVE PLAYERS SENT:",
            [p["name"] for p in active_players]
        )

        socketio.emit(
            "room_update",
            active_players,
            room=room_id
        )

        if len(
            rooms[room_id]["players"]
        ) == 0:

            del rooms[room_id]
@socketio.on("guess_word")
def guess_word(data):

    room_id = data["room_id"]

    guess = data["guess"].strip().lower()

    correct_word = (
        rooms[room_id]["civilian_word"]
        .strip()
        .lower()
    )

    if guess == correct_word:

        socketio.emit(
            "winner",
            f"Mr. White Wins! The word was {correct_word}",
            room=room_id
        )

        return

    # Mr. White guessed wrong

    if not rooms[room_id]["undercover_alive"]:

        socketio.emit(
            "winner",
            f"Civilians Win! The word was {correct_word}",
            room=room_id
        )

        return

    socketio.emit(
        "result",
        "Mr. White guessed wrong. Game continues.",
        room=room_id
    )

    rooms[room_id]["round"] += 1

    socketio.emit(
        "round_update",
        rooms[room_id]["round"],
        room=room_id
    )

    active_players = []

    for player in rooms[room_id]["players"]:

        if (
            player["sid"]
            not in rooms[room_id]["eliminated_players"]
        ):

            active_players.append(player)

    players_for_order = active_players.copy()

    random.shuffle(players_for_order)

    rooms[room_id]["clue_order"] = [

        p["sid"]

        for p in players_for_order

    ]

    rooms[room_id]["current_turn"] = 0

    if len(
        rooms[room_id]["clue_order"]
    ) > 0:

        first_sid = (
            rooms[room_id]["clue_order"][0]
        )

        socketio.emit(
            "your_turn",
            to=first_sid
        )

    rooms[room_id]["clues"] = []
    rooms[room_id]["votes"] = {}

    socketio.emit(
        "new_round",
        room=room_id
    )
if __name__ == "__main__":

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True
    )
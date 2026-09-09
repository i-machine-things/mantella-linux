"""Standalone test: exercises the LLM + TTS pipeline directly, without Skyrim.
Run from the Mantella source dir: ./MantellaEnv/bin/python test_pipeline.py
"""
import sys
sys.path.insert(0, '.')

from src.config.config_loader import ConfigLoader
from src.llm.llm_client import LLMClient
from src.llm.message_thread import message_thread
from src.llm.messages import UserMessage
from src.tts.tts_factory import create_tts
from src.tts.synthesization_options import SynthesizationOptions
from src.games.skyrim import Skyrim

MYGAMES = "/home/allan/Documents/My Games/Mantella"

config = ConfigLoader(MYGAMES)

print(f"LLM service: {config.llm_api}, model: {config.llm}")
llm = LLMClient(config)

thread = message_thread(config, "You are Ralof, a Stormcloak soldier from Skyrim. Reply in one short spoken sentence, no narration, no quotation marks.")
thread.add_message(UserMessage(config, "Hey Ralof, can you hear me?", player_character_name="Dragonborn"))

reply = llm.request_call(thread)
print(f"LLM reply: {reply!r}")

if not reply:
    print("LLM returned an empty response - stopping before TTS.")
    sys.exit(1)

if "--espeak-test" in sys.argv:
    reply = "Skyrim's borders aren't what they used to be, Dragonborn."
    print(f"Overriding with eSpeak-fallback test line: {reply!r}")

game = Skyrim(config)
tts = create_tts(config.tts_service, config, game)

options = SynthesizationOptions(aggro=False, is_first_line_of_response=True, stream_first_line=False)
wav_path, played_externally = tts.synthesize(
    voice="MaleNord",
    voiceline=reply,
    in_game_voice="MaleNord",
    csv_in_game_voice="MaleNord",
    voice_accent="en",
    synth_options=options,
)
print(f"Synthesized to: {wav_path}")
print(f"Played externally during synthesis: {played_externally}")

import asyncio
import os
import sys

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from runner import configure

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.services.openai import OpenAILLMContext, OpenAILLMService, OpenAILLMContextFrame
from pipecat.transports.services.daily import DailyParams, DailyTransport

load_dotenv(override=True)

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def start_put_on_hold(function_name, llm, context):
    """Inform the caller they're being put on hold."""
    await llm.push_frame(TTSSpeakFrame("I'll put you on hold while I check if they're available. Please hold."))
    logger.debug(f"Starting put_caller_on_hold")

async def put_caller_on_hold(function_name, tool_call_id, args, llm, context, result_callback):
    # Simulate a brief hold period
    await asyncio.sleep(2)
    await result_callback({"status": "on_hold", "message": "Caller has been put on hold"})

async def start_check_availability(function_name, llm, context):
    """Let the caller know we're checking availability."""
    await llm.push_frame(TTSSpeakFrame("Checking if they're available..."))
    logger.debug(f"Starting check_person_availability with function_name: {function_name}")

async def check_person_availability(function_name, tool_call_id, args, llm, context, result_callback):
    person_name = args.get("person_name", "")
    # Simulate checking availability - randomly determine if available
    import random
    is_available = random.choice([True, False])
    await asyncio.sleep(2)  # Simulate a delay for checking
    await result_callback({"is_available": is_available, "person_name": person_name})

async def start_transfer_call(function_name, llm, context):
    """Inform the caller they're being transferred."""
    await llm.push_frame(TTSSpeakFrame("Great news! I'm transferring you now. Please hold."))
    logger.debug(f"Starting transfer_call with function_name: {function_name}")

async def transfer_call(function_name, tool_call_id, args, llm, context, result_callback):
    person_name = args.get("person_name", "")
    # Simulate transferring the call
    await asyncio.sleep(3)
    await result_callback({"status": "transferred", "person_name": person_name})

async def start_take_message(function_name, llm, context):
    """Inform the caller we're taking a message."""
    await llm.push_frame(TTSSpeakFrame("I'll take a message for them."))
    logger.debug(f"Starting take_message with function_name: {function_name}")

async def take_message(function_name, tool_call_id, args, llm, context, result_callback):
    person_name = args.get("person_name", "")
    message = args.get("message", "")
    # Simulate recording a message
    await asyncio.sleep(1)
    await result_callback({"status": "message_recorded", "person_name": person_name})

class ReceptionistProcessor:
    def __init__(self, context: OpenAILLMContext):
        context.add_message(
            {
                "role": "system",
                "content": """You are a helpful receptionist for a legal company. Your job is to:
                1. Greet callers and ask who they would like to speak with. 
                The available people are:
                - John Doe
                - Jane Smith
                - Bob Johnson
                - Alice Brown
                2. Put them on hold while you check if the person is available
                3. If the person is available, transfer the call
                4. If the person is not available, offer to take a message
                
                Always be polite, professional, and efficient. Start by greeting the caller and asking who they'd like to speak with.
                
                When the caller provides a name, use the check_person_availability function.
                Before checking availability, use the put_caller_on_hold function.
                If the person is available, use the transfer_call function.
                If the person is not available, use the take_message function.
                
                Your output will be converted to audio so don't include special characters in your answers.""",
            }
        )
        context.set_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "put_caller_on_hold",
                        "description": "Put the caller on hold while checking for the requested person",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "check_person_availability",
                        "description": "Check if a person is available to take the call",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "person_name": {
                                    "type": "string",
                                    "description": "The name of the person to check availability for",
                                },
                            },
                            "required": ["person_name"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "transfer_call",
                        "description": "Transfer the call to the requested person",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "person_name": {
                                    "type": "string",
                                    "description": "The name of the person to transfer the call to",
                                },
                            },
                            "required": ["person_name"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "take_message",
                        "description": "Take a message for the unavailable person",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "person_name": {
                                    "type": "string",
                                    "description": "The name of the person to take a message for",
                                },
                                "message": {
                                    "type": "string",
                                    "description": "The message to be recorded",
                                },
                            },
                            "required": ["person_name", "message"],
                        },
                    },
                },
            ]
        )

async def main():
    async with aiohttp.ClientSession() as session:
        (room_url, token) = await configure(session)

        transport = DailyTransport(
            room_url,
            token,
            "Receptionist Bot",
            DailyParams(
                audio_out_enabled=True,
                transcription_enabled=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )

        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",  # British Lady
        )

        llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o")
        
        messages = []
        context = OpenAILLMContext(messages=messages)
        context_aggregator = llm.create_context_aggregator(context)
        
        # Initialize the receptionist processor
        receptionist = ReceptionistProcessor(context)
        
        # Register the receptionist functions
        llm.register_function("put_caller_on_hold", put_caller_on_hold, start_callback=start_put_on_hold)
        llm.register_function("check_person_availability", check_person_availability, start_callback=start_check_availability)
        llm.register_function("transfer_call", transfer_call, start_callback=start_transfer_call)
        llm.register_function("take_message", take_message, start_callback=start_take_message)

        pipeline = Pipeline(
            [
                transport.input(),
                context_aggregator.user(),
                llm,
                tts,
                transport.output(),
                context_aggregator.assistant(),
            ]
        )

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
                report_only_initial_ttfb=True,
            ),
        )

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            await transport.capture_participant_transcription(participant["id"])
            # Kick off the conversation.
            await task.queue_frames([OpenAILLMContextFrame(context)])

        runner = PipelineRunner()

        await runner.run(task)


if __name__ == "__main__":
    asyncio.run(main())
# DuoHub Transfer - AI Receptionist Bot

A virtual receptionist powered by AI that handles calls, checks availability, transfers calls, and takes messages. This project serves as a demonstration for legal companies on how to implement intelligent call transfers with VOIP systems.

## Overview

This project implements an AI-powered receptionist bot using the PipeCat AI framework and Daily.co for video/audio communication. The bot demonstrates how legal firms can automate their reception process to:

1. Greet callers and ask who they would like to speak with
2. Put callers on hold while checking availability
3. Transfer calls to available staff members
4. Take messages when staff members are unavailable

The system uses OpenAI's GPT-4o model for natural language understanding and generation, and Cartesia TTS for voice synthesis. While this example uses Daily.co for demonstration purposes, the same principles can be applied to any VOIP system.

## Prerequisites

- Python 3.12+
- Daily.co API key
- OpenAI API key
- Cartesia API key

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/duohub-transfer.git
   cd duohub-transfer
   ```

2. Install dependencies using Poetry:
   ```
   poetry install
   ```

3. Create a `.env` file with the following variables:
   ```
   DAILY_API_KEY=your_daily_api_key
   DAILY_SAMPLE_ROOM_URL=your_daily_room_url
   OPENAI_API_KEY=your_openai_api_key
   CARTESIA_API_KEY=your_cartesia_api_key
   ```

## Usage

### Running the Bot

To start the receptionist bot:

```
poetry run python bot.py
```

### Running the Server

To start the server that manages bot instances:

```
poetry run python server.py
```

The server provides the following endpoints:

- `GET /`: Start a new agent and redirect to the Daily room
- `POST /connect`: Connect an RTVI client to a bot
- `GET /status/{pid}`: Check the status of a bot process
- `POST /`: Join an existing room
- `GET /health`: Health check endpoint

## Architecture

The project consists of three main components:

1. **Bot (bot.py)**: Implements the AI receptionist logic using PipeCat and OpenAI
2. **Server (server.py)**: FastAPI server that manages bot instances and provides endpoints
3. **Runner (runner.py)**: Helper module for configuring Daily rooms and tokens

The bot uses a pipeline architecture with the following components:
- Daily.co for audio/video communication
- Silero VAD for voice activity detection
- OpenAI GPT-4o for natural language processing
- Cartesia TTS for text-to-speech conversion

## Call Transfer Process

This example demonstrates a complete call transfer workflow for legal firms:

1. **Initial Greeting**: The AI receptionist greets the caller and asks who they'd like to speak with
2. **Availability Check**: The system checks if the requested staff member is available
3. **Hold Management**: The caller is placed on hold during the availability check
4. **Call Transfer**: If the staff member is available, the call is transferred
5. **Message Taking**: If unavailable, the system offers to take a message

This workflow can be integrated with existing VOIP systems used by legal firms to automate their reception process.

## Available Staff

For demonstration purposes, the receptionist can connect callers to:
- John Doe
- Jane Smith
- Bob Johnson
- Alice Brown

## Integration with VOIP Systems

While this example uses Daily.co, the same principles can be applied to integrate with popular VOIP systems used by legal firms. The key components for integration are:

1. **Audio Input/Output**: Capturing caller audio and playing synthesized responses
2. **Call Control**: Ability to place calls on hold and transfer to different extensions
3. **Status Monitoring**: Checking availability of staff members

## Customization for Legal Firms

Legal firms can customize this example by:
- Adding their specific staff directory
- Customizing the greeting and messaging scripts
- Integrating with their case management systems
- Adding authentication for sensitive client interactions


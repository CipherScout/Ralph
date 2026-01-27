"""AsyncInputReader - Platform-aware non-blocking input with cancellation support.

This module provides asynchronous input reading that works across Unix and Windows
platforms, supporting task cancellation and non-blocking operation.
"""

from __future__ import annotations

import asyncio
import platform
import sys

# Platform-specific imports
if platform.system() == "Windows":
    try:
        import msvcrt
    except ImportError:
        msvcrt = None  # type: ignore[assignment]


class AsyncInputReader:
    """Platform-aware asynchronous input reader with cancellation support.

    This class provides a unified interface for reading user input asynchronously
    across different platforms (Unix/Linux/macOS and Windows), while supporting
    task cancellation for responsive applications.

    The implementation uses platform-specific approaches:
    - Unix/Linux/macOS: Uses asyncio's run_in_executor with sys.stdin.readline
    - Windows: Uses polling with msvcrt.kbhit() and msvcrt.getch()

    Example:
        reader = AsyncInputReader()
        try:
            user_input = await reader.read_input("Enter your name: ")
            print(f"Hello, {user_input}!")
        except asyncio.CancelledError:
            print("Input was cancelled")
    """

    def __init__(self) -> None:
        """Initialize the AsyncInputReader."""
        self._platform = platform.system()

    async def read_input(self, prompt: str = "") -> str:
        """Read input asynchronously with platform-specific implementation.

        Args:
            prompt: The prompt to display to the user

        Returns:
            The user's input as a string

        Raises:
            asyncio.CancelledError: If the operation is cancelled
        """
        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()

        return await self._platform_read_input(prompt)

    async def _platform_read_input(self, prompt: str) -> str:
        """Select platform-specific input reading method.

        Args:
            prompt: The prompt string (for consistency with platform methods)

        Returns:
            The user's input
        """
        if self._platform == "Windows":
            return await self._windows_read_input(prompt)
        else:
            return await self._unix_read_input(prompt)

    async def _unix_read_input(self, prompt: str) -> str:
        """Unix/Linux/macOS implementation using run_in_executor.

        Args:
            prompt: The prompt string (unused in this implementation)

        Returns:
            The user's input with newline preserved
        """
        loop = asyncio.get_event_loop()

        # Use run_in_executor to make blocking readline non-blocking
        input_text = await loop.run_in_executor(None, sys.stdin.readline)

        return str(input_text)

    async def _windows_read_input(self, prompt: str) -> str:
        """Windows implementation using polling with msvcrt.

        Args:
            prompt: The prompt string (unused in this implementation)

        Returns:
            The user's input as a single character
        """
        if msvcrt is None:
            # Fallback to Unix behavior if msvcrt is not available
            return await self._unix_read_input(prompt)

        # Poll for input without blocking
        while True:
            if msvcrt.kbhit():  # type: ignore[attr-defined]
                # Key is available, read it
                key = msvcrt.getch()  # type: ignore[attr-defined]
                char = key.decode('utf-8', errors='ignore') if isinstance(key, bytes) else str(key)

                # Echo the character (msvcrt.getch doesn't echo)
                sys.stdout.write(char)
                sys.stdout.flush()

                return char

            # No key available, yield control and check for cancellation
            await asyncio.sleep(0.01)  # Small delay to prevent busy waiting

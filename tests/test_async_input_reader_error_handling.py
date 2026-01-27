"""Tests for AsyncInputReader error handling - EOFError, KeyboardInterrupt, and platform edge cases."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from ralph.async_input_reader import AsyncInputReader


class TestAsyncInputReaderErrorHandling:
    """Test cases for AsyncInputReader error handling scenarios."""

    @pytest.mark.asyncio
    async def test_eoferror_handling_unix(self):
        """Test EOFError handling in Unix implementation."""
        reader = AsyncInputReader()

        # Mock the executor to raise EOFError
        async def mock_executor_eof(executor, func):
            raise EOFError("No more input available")

        with patch('ralph.async_input_reader.asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.side_effect = mock_executor_eof

            with pytest.raises(EOFError):
                await reader._unix_read_input("Test: ")

    @pytest.mark.asyncio
    async def test_eoferror_handling_windows_fallback(self):
        """Test EOFError handling when Windows falls back to Unix method."""
        reader = AsyncInputReader()

        # Mock the Windows platform but with msvcrt as None to trigger fallback
        with patch('ralph.async_input_reader.platform.system', return_value='Windows'):
            # Create a fresh module-level msvcrt None for Windows fallback testing
            with patch.dict('ralph.async_input_reader.__dict__', {'msvcrt': None}):
                # Mock the Unix fallback executor to raise EOFError
                async def mock_executor_eof(executor, func):
                    raise EOFError("No more input available")

                with patch('ralph.async_input_reader.asyncio.get_event_loop') as mock_loop:
                    mock_loop.return_value.run_in_executor.side_effect = mock_executor_eof

                    with pytest.raises(EOFError):
                        await reader._windows_read_input("Test: ")

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_handling_unix(self):
        """Test KeyboardInterrupt handling in Unix implementation."""
        reader = AsyncInputReader()

        # Mock the executor to raise KeyboardInterrupt
        async def mock_executor_interrupt(executor, func):
            raise KeyboardInterrupt("User cancelled")

        with patch('ralph.async_input_reader.asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor.side_effect = mock_executor_interrupt

            with pytest.raises(KeyboardInterrupt):
                await reader._unix_read_input("Test: ")

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_handling_windows(self):
        """Test KeyboardInterrupt handling in Windows implementation."""
        reader = AsyncInputReader()

        with patch('ralph.async_input_reader.msvcrt', create=True) as mock_msvcrt:
            # Mock kbhit to raise KeyboardInterrupt
            mock_msvcrt.kbhit.side_effect = KeyboardInterrupt("Ctrl+C pressed")

            with pytest.raises(KeyboardInterrupt):
                await reader._windows_read_input("Test: ")

    @pytest.mark.asyncio
    async def test_eoferror_in_read_input_method(self):
        """Test that EOFError in read_input is handled appropriately."""
        reader = AsyncInputReader()

        # Mock platform read to raise EOFError
        async def mock_platform_eof(prompt):
            raise EOFError("End of file reached")

        with patch.object(reader, '_platform_read_input', side_effect=mock_platform_eof):
            with pytest.raises(EOFError):
                await reader.read_input("Enter something: ")

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_in_read_input_method(self):
        """Test that KeyboardInterrupt in read_input is handled appropriately."""
        reader = AsyncInputReader()

        # Mock platform read to raise KeyboardInterrupt
        async def mock_platform_interrupt(prompt):
            raise KeyboardInterrupt("Interrupted by user")

        with patch.object(reader, '_platform_read_input', side_effect=mock_platform_interrupt):
            with pytest.raises(KeyboardInterrupt):
                await reader.read_input("Enter something: ")

    @pytest.mark.asyncio
    async def test_windows_msvcrt_unavailable_fallback(self):
        """Test Windows fallback when msvcrt is unavailable."""
        with patch('ralph.async_input_reader.platform.system', return_value='Windows'):
            # Create reader with mocked Windows platform but no msvcrt
            with patch.dict('ralph.async_input_reader.__dict__', {'msvcrt': None}):
                reader = AsyncInputReader()

                # Mock Unix fallback
                async def mock_unix_fallback(prompt):
                    return "fallback input"

                with patch.object(reader, '_unix_read_input', side_effect=mock_unix_fallback) as mock_unix:
                    result = await reader._windows_read_input("Test: ")
                    mock_unix.assert_called_once_with("Test: ")
                    assert result == "fallback input"

    @pytest.mark.asyncio
    async def test_platform_specific_exception_handling(self):
        """Test handling of platform-specific exceptions."""
        reader = AsyncInputReader()

        # Test handling of various system exceptions
        class CustomSystemError(Exception):
            pass

        async def mock_platform_system_error(prompt):
            raise CustomSystemError("Platform specific error")

        with patch.object(reader, '_platform_read_input', side_effect=mock_platform_system_error):
            with pytest.raises(CustomSystemError):
                await reader.read_input("Enter something: ")

    @pytest.mark.asyncio
    async def test_non_tty_environment_handling(self):
        """Test behavior in non-TTY environments."""
        reader = AsyncInputReader()

        # Mock sys.stdin.isatty() to return False and test non-interactive behavior
        with patch('ralph.async_input_reader.sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.readline.return_value = "non-tty input\n"

            # Mock the executor call
            async def mock_executor(executor, func):
                return func()

            with patch('ralph.async_input_reader.asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor.side_effect = mock_executor

                result = await reader._unix_read_input("Test: ")
                assert result.strip() == "non-tty input"

    @pytest.mark.asyncio
    async def test_windows_decode_error_handling(self):
        """Test handling of decode errors in Windows implementation."""
        reader = AsyncInputReader()

        with patch('ralph.async_input_reader.msvcrt', create=True) as mock_msvcrt:
            # Mock kbhit and getch with problematic byte sequence
            mock_msvcrt.kbhit.side_effect = [False, False, True]
            mock_msvcrt.getch.return_value = b'\xff'  # Invalid UTF-8

            with patch('ralph.async_input_reader.sys.stdout') as mock_stdout:
                result = await reader._windows_read_input("Test: ")
                # Should handle decode error gracefully
                assert isinstance(result, str)
                mock_stdout.write.assert_called()

    @pytest.mark.asyncio
    async def test_unix_stdin_read_error_handling(self):
        """Test handling of stdin read errors in Unix implementation."""
        reader = AsyncInputReader()

        # Mock stdin.readline to raise an IOError
        with patch('ralph.async_input_reader.sys.stdin') as mock_stdin:
            mock_stdin.readline.side_effect = OSError("stdin read error")

            async def mock_executor(executor, func):
                return func()

            with patch('ralph.async_input_reader.asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor.side_effect = mock_executor

                with pytest.raises(IOError):
                    await reader._unix_read_input("Test: ")

    @pytest.mark.asyncio
    async def test_asyncio_cancelled_error_propagation(self):
        """Test that asyncio.CancelledError is properly propagated."""
        reader = AsyncInputReader()

        # Mock platform read to raise CancelledError
        async def mock_platform_cancelled(prompt):
            raise asyncio.CancelledError("Task was cancelled")

        with patch.object(reader, '_platform_read_input', side_effect=mock_platform_cancelled):
            with pytest.raises(asyncio.CancelledError):
                await reader.read_input("Enter something: ")

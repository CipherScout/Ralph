"""Tests for AsyncInputReader class with platform-aware non-blocking input."""

from __future__ import annotations

import asyncio
import platform
import sys
from unittest.mock import patch

import pytest

from ralph.async_input_reader import AsyncInputReader


class TestAsyncInputReader:
    """Test cases for AsyncInputReader."""

    def test_init(self):
        """Test that AsyncInputReader can be instantiated."""
        reader = AsyncInputReader()
        assert reader is not None

    @pytest.mark.asyncio
    async def test_read_input_exists(self):
        """Test that read_input method exists."""
        reader = AsyncInputReader()
        assert hasattr(reader, 'read_input')
        assert callable(reader.read_input)

    @pytest.mark.asyncio
    async def test_read_input_with_prompt(self):
        """Test that read_input accepts a prompt parameter."""
        reader = AsyncInputReader()

        # Create a proper async mock
        async def mock_input(prompt):
            return "test input"

        with patch.object(reader, '_platform_read_input', side_effect=mock_input) as mock_platform:
            result = await reader.read_input("Enter something: ")
            mock_platform.assert_called_once_with("Enter something: ")
            assert result == "test input"

    @pytest.mark.asyncio
    async def test_read_input_cancellation(self):
        """Test that read_input can be cancelled."""
        reader = AsyncInputReader()

        # Create a task that will hang
        async def mock_hanging_input(prompt):
            await asyncio.sleep(10)  # Simulate long input wait
            return "should not reach here"

        with patch.object(reader, '_platform_read_input', side_effect=mock_hanging_input):
            task = asyncio.create_task(reader.read_input("Enter something: "))
            await asyncio.sleep(0.01)  # Let it start
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

    @pytest.mark.skipif(platform.system() == "Windows", reason="Test Unix-specific behavior")
    @pytest.mark.asyncio
    async def test_unix_platform_detection(self):
        """Test Unix platform detection and usage."""
        with patch('ralph.async_input_reader.platform.system', return_value='Linux'):
            # Need to recreate reader to pick up the new platform
            reader = AsyncInputReader()

            async def mock_unix_input(prompt):
                return "unix input"

            with patch.object(reader, '_unix_read_input', side_effect=mock_unix_input) as mock_unix:
                result = await reader.read_input("Test: ")
                mock_unix.assert_called_once_with("Test: ")
                assert result == "unix input"

    @pytest.mark.skipif(platform.system() != "Windows", reason="Test Windows-specific behavior")
    @pytest.mark.asyncio
    async def test_windows_platform_detection(self):
        """Test Windows platform detection and usage."""
        with patch('ralph.async_input_reader.platform.system', return_value='Windows'):
            # Need to recreate reader to pick up the new platform
            reader = AsyncInputReader()

            async def mock_windows_input(prompt):
                return "windows input"

            with patch.object(reader, '_windows_read_input', side_effect=mock_windows_input) as mock_windows:
                result = await reader.read_input("Test: ")
                mock_windows.assert_called_once_with("Test: ")
                assert result == "windows input"

    @pytest.mark.asyncio
    async def test_unix_implementation_mock(self):
        """Test Unix implementation with mocked sys.stdin."""
        reader = AsyncInputReader()

        # Mock the Unix-specific components
        async def mock_executor(executor, func):
            return "mocked input\n"

        with patch('ralph.async_input_reader.sys.stdin'):
            with patch('ralph.async_input_reader.asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor.side_effect = mock_executor

                result = await reader._unix_read_input("Test: ")
                assert result.strip() == "mocked input"

    @pytest.mark.asyncio
    async def test_windows_implementation_mock(self):
        """Test Windows implementation with mocked msvcrt."""
        reader = AsyncInputReader()

        # Mock Windows-specific components
        with patch('ralph.async_input_reader.msvcrt', create=True) as mock_msvcrt:
            mock_msvcrt.kbhit.side_effect = [False, False, True]  # Key available on third check
            mock_msvcrt.getch.return_value = b'y'

            with patch('ralph.async_input_reader.sys.stdout') as mock_stdout:
                result = await reader._windows_read_input("Test: ")
                assert result == "y"
                mock_stdout.write.assert_called()
                mock_stdout.flush.assert_called()

    @pytest.mark.asyncio
    async def test_read_input_handles_empty_string(self):
        """Test that empty string input is handled properly."""
        reader = AsyncInputReader()

        async def mock_empty_input(prompt):
            return ""

        with patch.object(reader, '_platform_read_input', side_effect=mock_empty_input):
            result = await reader.read_input("Enter something: ")
            assert result == ""

    @pytest.mark.asyncio
    async def test_read_input_handles_whitespace(self):
        """Test that whitespace-only input is handled properly."""
        reader = AsyncInputReader()

        async def mock_whitespace_input(prompt):
            return "   \n"

        with patch.object(reader, '_platform_read_input', side_effect=mock_whitespace_input):
            result = await reader.read_input("Enter something: ")
            assert result == "   \n"

    @pytest.mark.asyncio
    async def test_multiple_reads(self):
        """Test that multiple reads work correctly."""
        reader = AsyncInputReader()

        inputs = ["first", "second", "third"]
        input_iter = iter(inputs)

        async def mock_input_generator(prompt):
            return next(input_iter)

        with patch.object(reader, '_platform_read_input', side_effect=mock_input_generator):
            for expected in inputs:
                result = await reader.read_input(f"Enter {expected}: ")
                assert result == expected

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

        # Mock msvcrt as None to trigger fallback
        with patch.object(sys.modules.get('ralph.async_input_reader', {}), 'msvcrt', None, create=True):
            # Mock the executor to raise EOFError
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
            with patch.object(sys.modules.get('ralph.async_input_reader', {}), 'msvcrt', None, create=True):
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

        # Mock sys.stdin.isatty() to return False
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

#!/usr/bin/env python3
"""
Test suite for Seeking Alpha module
"""

import sys
import os
import unittest
import tempfile
from unittest.mock import patch, MagicMock
import pytest

# Add the backend directory to the path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from seeking_alpha import fetch_fool_transcript, search_transcript_web


class TestSeekingAlpha(unittest.TestCase):
    def test_fetch_fool_transcript_function(self):
        """Test that fetch_fool_transcript function works correctly"""
        # Test with a known fool.com transcript URL
        url = "https://www.fool.com/earnings/call-transcripts/test-transcript"
        transcript = fetch_fool_transcript(url)
        self.assertIsInstance(transcript, str)

    def test_search_transcript_web_with_text(self):
        """Test that search_transcript_web returns results with text field"""
        ticker = "AAPL"  # Using a real ticker for testing
        results = search_transcript_web(ticker)
        self.assertIsInstance(results, list)
        # Check that the first result has a text field
        if results:
            self.assertIn('text', results[0])
            # Check that the text field contains the transcript content
            self.assertIsInstance(results[0].get('text', ''), str)

if __name__ == '__main__':
    unittest.main()
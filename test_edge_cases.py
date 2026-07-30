#!/usr/bin/env python3
"""Test script to verify edge cases for BM25Index.delete() fix."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from tool.RAGTool.app.sparse.bm25_index import BM25Index

def test_edge_cases():
    """Test various edge cases for the delete method."""
    
    # Create index and add some documents
    index = BM25Index()
    index.add_many([
        ("doc1", "content one"),
        ("doc2", "content two"), 
        ("doc3", "content three")
    ])
    
    print("Initial state:")
    print(f"doc_ids length: {len(index._doc_ids)}")
    print(f"doc_term_freqs length: {len(index._doc_term_freqs)}")
    print(f"doc_lengths length: {len(index._doc_lengths)}")
    print(f"id_to_index: {index._id_to_index}")
    
    # Test 1: Delete existing document
    print("\n--- Test 1: Delete existing document ---")
    index.delete("doc2")
    print(f"After deleting doc2:")
    print(f"doc_ids length: {len(index._doc_ids)}")
    print(f"doc_term_freqs length: {len(index._doc_term_freqs)}")
    print(f"doc_lengths length: {len(index._doc_lengths)}")
    print(f"id_to_index: {index._id_to_index}")
    
    # Verify all lists are synchronized
    assert len(index._doc_ids) == len(index._doc_term_freqs) == len(index._doc_lengths) == 2
    assert "doc2" not in index._id_to_index
    assert index._doc_ids == ["doc1", "doc3"]
    print("✓ All lists properly synchronized after deletion")
    
    # Test 2: Try to delete non-existing document
    print("\n--- Test 2: Delete non-existing document ---")
    index.delete("nonexistent")
    print("Should have logged a warning about nonexistent document")
    
    # Test 3: Delete remaining documents
    print("\n--- Test 3: Delete remaining documents ---")
    index.delete("doc1")
    print(f"After deleting doc1:")
    print(f"doc_ids length: {len(index._doc_ids)}")
    print(f"doc_term_freqs length: {len(index._doc_term_freqs)}")
    print(f"doc_lengths length: {len(index._doc_lengths)}")
    print(f"id_to_index: {index._id_to_index}")
    
    index.delete("doc3")
    print(f"After deleting doc3:")
    print(f"doc_ids length: {len(index._doc_ids)}")
    print(f"doc_term_freqs length: {len(index._doc_term_freqs)}")
    print(f"doc_lengths length: {len(index._doc_lengths)}")
    print(f"id_to_index: {index._id_to_index}")
    
    # Verify all lists are empty
    assert len(index._doc_ids) == len(index._doc_term_freqs) == len(index._doc_lengths) == 0
    assert len(index._id_to_index) == 0
    print("✓ All documents properly removed, no placeholders left")
    
    print("\n=== All edge case tests passed! ===")

if __name__ == "__main__":
    test_edge_cases()
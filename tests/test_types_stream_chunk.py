from tawn.model.types import StreamChunk


def test_stream_chunk_defaults():
    chunk = StreamChunk(text="hi")
    assert chunk.done is False
    assert chunk.tokens_in is None
    assert chunk.tokens_out is None
    assert chunk.error is None


def test_stream_chunk_final():
    chunk = StreamChunk(text="", done=True, tokens_in=9, tokens_out=4)
    assert chunk.done is True
    assert chunk.tokens_in == 9 and chunk.tokens_out == 4


def test_stream_chunk_error():
    chunk = StreamChunk(text="partial ", done=True, error="server_error")
    assert chunk.error == "server_error"

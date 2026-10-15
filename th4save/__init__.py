"""th4save - read/write The Hell 4 (vanilla, v0.77x) single-player save archives.

Pipeline:  .ssv (MPQ v1) -> sector explode (PKWARE DCL) -> Diablo save codec
(SHA-XOR, password 'xrgyrkj1') -> PlayerInfo_v26 (11,798 bytes).
"""
__version__ = "0.1.0"

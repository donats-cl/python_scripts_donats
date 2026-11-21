import base64
import io
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

import grpc_tools
import zstandard as zstd
from google.protobuf.json_format import MessageToDict, ParseDict
from grpc_tools import protoc

BASE_DIR = Path(__file__).resolve().parent / "_deadlock_protos"
RAW_DIR = BASE_DIR / "src"
OUT_DIR = BASE_DIR / "gen"

PROTO_SOURCES = [
    "https://raw.githubusercontent.com/SteamDatabase/Protobufs/master/deadlock/",
    "https://raw.githubusercontent.com/SteamTracking/GameTracking-Deadlock/master/Protobufs/",
]


def strip_valve_options(text: str) -> str:
    # Убираем файловые опции Valve, которых нет в стандартном descriptor.proto
    text = re.sub(
        r'\boption\s+(?:additional_includes|php_output_subdir)\s*=\s*"[^"]*"\s*;',
        "",
        text,
    )

    # Убираем полевые опции Valve внутри [...], сохраняя стандартные (default, packed и т.д.)
    def clean_brackets(m: re.Match) -> str:
        inner = m.group(1)
        inner = re.sub(r'\bboxed_type\s*=\s*"[^"]*"\s*,?', "", inner)
        inner = re.sub(r"\bsynthetic_default\s*=\s*[^,\]]+\s*,?", "", inner)
        inner = re.sub(r",\s*$", "", inner.strip())
        inner = re.sub(r"^\s*,", "", inner).strip()
        return f"[{inner}]" if inner else ""

    text = re.sub(
        r"\[([^\]]*\b(?:boxed_type|synthetic_default)\b[^\]]*)\]",
        clean_brackets,
        text,
    )
    return text


def download_file(filename: str) -> Path:
    dest = RAW_DIR / filename
    if dest.exists():
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err = None
    for base_url in PROTO_SOURCES:
        url = base_url + filename
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "python-deadlock-build"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            dest.write_text(strip_valve_options(text), encoding="utf-8")
            print(f"Downloaded: {filename}")
            return dest
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Failed to download {filename}: {last_err}")


def ensure_protos():
    pb_file = OUT_DIR / "citadel_gcmessages_common_pb2.py"

    if not pb_file.exists():
        shutil.rmtree(RAW_DIR, ignore_errors=True)
        shutil.rmtree(OUT_DIR, ignore_errors=True)
        OUT_DIR.mkdir(parents=True, exist_ok=True)

        visited = set()

        def fetch_recursive(filename: str):
            if filename in visited or filename.startswith("google/protobuf/"):
                return
            visited.add(filename)
            path = download_file(filename)
            text = path.read_text(encoding="utf-8", errors="replace")
            imports = re.findall(
                r'^\s*import\s+(?:public\s+|weak\s+)?"([^"]+)"\s*;', text, re.M
            )
            for imp in imports:
                fetch_recursive(imp)

        fetch_recursive("citadel_gcmessages_common.proto")

        grpc_proto_dir = os.path.join(os.path.dirname(grpc_tools.__file__), "_proto")
        proto_files = [str(RAW_DIR / f) for f in sorted(visited)]
        args = [
            "grpc_tools.protoc",
            f"-I{RAW_DIR}",
            f"-I{grpc_proto_dir}",
            f"--python_out={OUT_DIR}",
            *proto_files,
        ]
        rc = protoc.main(args)
        if rc != 0:
            raise RuntimeError(f"protoc failed with exit code {rc}")

    if str(OUT_DIR) not in sys.path:
        sys.path.insert(0, str(OUT_DIR))


ensure_protos()
import citadel_gcmessages_common_pb2 as pb  # noqa: E402


def decode_build(code: str) -> dict:
    raw = base64.b64decode(code.strip())
    dctx = zstd.ZstdDecompressor()
    with dctx.stream_reader(io.BytesIO(raw)) as reader:
        proto_bytes = reader.read()

    msg = pb.CMsgHeroBuild()
    msg.ParseFromString(proto_bytes)
    return MessageToDict(msg, preserving_proto_field_name=True)


def encode_build(data: dict) -> str:
    msg = ParseDict(data, pb.CMsgHeroBuild())
    proto_bytes = msg.SerializeToString()

    cctx = zstd.ZstdCompressor(level=3)
    compressed = cctx.compress(proto_bytes)
    return base64.b64encode(compressed).decode("ascii")


if __name__ == "__main__":
    EMPTY_BUILD = "KLUv/SBe8QIACDoQPBimofbmAyCysobYBiocQ29weSBvZiBbTmV3IFNpbmNsYWlyIEJ1aWxkXTIAOABAAFIoCiYSHSNDaXRhZGVsX0hlcm9CdWlsZHNfRWFybHlHYW1lGgAlAAAWRA=="

    NORMAL_BUILD = "KLUv/WB7IJ10AMpbXBVJcBpWBwPEpGFhoG72YxLhwB0AmCQhKWt97wE5pcMOupUpH5KvuSA6V9+WEucbxjjL1xa+S980eYwURuy/EBcjmZHcVQBfLha5STEBQgFEAZ71SiwkO6fGh5Yw3aYJn3yownKefjaGT3AhbPRdo9e3y23zVHNji263eoqi0TPo870e69F+6mbfi0Ae3MRDcud7zxSN2cde+TaW2d1asXQh020SY/xWhy7nGNbr1OxCGfaAqjVYJhpEUn5lHyryqfX97CFI46PVq6Rm7MOY3U1adX07Y+OM/dCSptus3C0+zmg/fYdOX8qnT/UZ8/E4G6OPnIXcOMdJOfrXd+tP//pV8/Sr7641npqpj/3se9dzfY/v+hzHGTk79eM/zu7GL7/ZR984Q9+Pc/Tln5rL3rF//Rlz9bG//NbIHlB2Rm1Nt58DoCXHoQdSgxg5Ptw03CjciJg6gDjyEkreYQQIJdd5ktIGEiWOltwp6C2Ewd0CBzlqU7qkuc2WMU8eCQ4UGNIBUU5AWAUQLvJ+vB7R16II/+AUvKEP+Ita0QRMep96PiR/hTwkH9QwqBTk9VkP5D1YBQ/Kfz4hET4a+pqafMMnohfhISwkOgadGyG3eHzD4O4GWiaNMqXVL2tyrj4fJ90AtIKwUWnckCCkW8V+2DprYdUfGskq+srQafNbrU0ga8gXsONVlmazH33JyF6s+V+tj40jM6aFTbdyTDVLoaFZnU/mt9EtRbLoVojDmGeIMWMITYN+KOiAzKBn2H3zxLJ21S2SHIBobmdD6qbbkd1uP9Pro31sFWefA48PiqfCfUCeiJ19s5p1RNJHsXXGokFkDedwpF5mjgDdnKkIDA6dvOkX7PlVGfQqyy+FpahshV4lZ5etZquZ1+OYu40mWVJF43Rk3aV+9MX8oMn1TWderz06nH6jK8zGK5/5vuOB/NbzAzSW3xLZNmLmK2F02ySn4yV3G9qFIW88TFtv/K+lj+wV3IZP7ONMS78dx1afrvepWvD9UvBMOHTE0dUOIARMU6lxWkzDYBFOAT9l5SVSqUMzs5qXPGkEDrsFSK05wTQOyW/o27nKH9o7UjPXINooxwunrwf0/WCilKt8rK/xzVbKFiAmVlNGt1h6MkCn7vEF1g6cJREwLSDMwpsawO4+RQEDbJwcT7AgGkFOs+V2XFTuImHQiUhyvQge348HhD3k7JuRedw2chhyjG5pAFkEgz1/iUDesLh0sy/cAWosudK0ix4dU1X5EXxJdn5b3QJ8sNUY0+0S6xGDpKPbg4tDXsz1vT1Aqw1JU0NRidzFIqsf/3KWoVcqkE+nZp8K3tDoGn/Y46TsHCpGK1TjsOT0VW5HvZVJ3X6C3IXCYJEIjHIrEJVMDDlqaVXYnk4YMJuCPXECzZo254vYETArU2pibVsCXIGdJpQLGn0gh/O1jxAcTQm5/eigPf7plN2iE7ycrWhLUhntjeDvDvnsqxn/DEEQmi4lmW3hqL5E/jJRTYnFILHFiJc4peqAoNPGQxTCSg+snm9ga6+rbG/I00mgSuChvvIH7B2pLE+WO1SgODnqNM20dd0Yia5ZonOOc9UcRdQ1wVBeBQzCxR78c3LiudaY67za5s5xQpHK0O3XNf6sV7BvorRFceqfB8YXeWynG9cD6oOLbom8yfmK+Rt2zhoYGjx0iNyNk1w7tGMa3Xy/Tq4n83IpkBeJMNE3dCenqBS+Jg+aoCsC0r0vTskGoCPNmhKNk/I6H4f7U0SExLobFKUC+Y8ECa7z4MEEhw5HYjde6zllpHvqFYdsHTAnyarGMcmdYX3R1kg1Ji/0hRrJrbd6DISLqFM6S6fUiMiMFiRJmgNjUCAgMEgsp5SL3B5jQhZSoOcockiJmCgpKChJaw1jNP1S3eGq6/6nUiw8lYS2/2tU56fQaYoWZVXzwmcZt2sxUCtY2OhXEVgHFFswCywCjEAZaivJQhYreW0SGf3NmAMRAzEQ5pozLyf4oF4XQW/tpWTNedgLz5nRcFmd8rmNknoONDQkGXTKx9ZcA4FcRCHtFgQxfToiAafZ6UgcPi4oY1f6aTNWL5bcQEYRsE/zYXRQBWXDvkmtmCCYFMpzSEQ2XdV/1PxsN9B5c3UYL53FHXXKnCJo+FSCsdrwM++hzZKlip1lUNygT7CccB28hr/OhntGsF6RLb/GGGTdUNXyS08270KfIZNmjpDnx/4ZSAhvHkAjFiuDcieGFFtTu7/H3ycmnGEgOn71oAn1zJb0NbrT1slj20oPj8zCeaLAdLjb0Fvomp18uivP414+31GD6FNX5Z14gc9RTFumoiNjiMxnqdut7pxMZLPhRd9mjxjCMoOEGkKuRQhyxSEqW6xDAGE41iEdK2dU7mCxIrgzbUgvcfwEmJgQKyyimfqhrE8OklZF/wpkoaAXi0jDo+AnJFTKP86EbHX1qJ0q8LIqCXIwo17Xn/q6vL46SymXjtq60mnKGeIGcEeYRmnNAhs8b2mU//DGw3MImYSCGx89W3650tGKugrvjFTDxWJXb4lnJQN2V7RFu9ez0eR6TKpP0vTBMOj0mAg4Cy4zyfBF5mO4BFjD4CaGoty1JyjRjA15Y/uOJHDLr3XcQ5ya5xsrVa03+H0HUMQ+nFudHKnQ/qVXK9GliVtDxLslZUFph/eUVP4zGlZcNwpK+opxBpdfnDhC4eYZ2EvpTFo+wBICpImoVWx5HuMQkriE+9UMEKk0nvw3a5VuILFVg8HdjLGM871xlJNkJaeIfH0i/BqgUd6EdTEhU0Y6fJ7WHzSuZJZmQSHbYO2n1CA0mezXT09FkZUVDuw6mPHzpxxlTswpIbwMlQaVnS5RZ9jYXzkUGUAbOe0i9XCPitx2dssoJn5EjGRaxduUWc4s1h2i0GDcD+zeP9itrMF7CFc1U0dxgzKoXjWMrxWeqD0K5jFYfgQjj696szRWAfgbj365GCJd6NKxZeBkOXA6gKabwKBmUDfUMuCOteO5tQLv4zdi00dk3IQJWB/ji+hPjN0a7qif8eWecF9VehyoFIIrPIXyH8kvSQsik3dOG/QWVsAuv1dWg//Fy2+sCNI4abpVlVRw0Kn/AWjyMKSqP/gJ4SvMbJri7C9RBXwW2YT4SrW2tFMNh1yZ0hOMhqoGemz3yeHnEq9RX+MTumgXH+p+e40lXJKgNjBXCVB0QMAUcpXipMXTZs9ztmEbfDn0mRqWB/CA07W6Vn8K5ieylrWlKNZ1+QIzoYZMgD8DiovxcOAyqO7JVtj1BJ0KmlTWovMIIJSWsRrfkh06PK2J7rbZdWaNGMU3LxccrSSPfxSakf80uMSfh7ayD5EH0k1FTRStsbxISKblDGEzC2ldsvAbhhnY7KJsLmc2UYJHzg6TlTQKmL1kuurzU/icLHHs/zLVjegp5K5EKkXb6ATSFVUr99pKNdIS3xr+lFwz06DY0nYIbBux1gWd3JwVfqKt7x1TsM0cBxIuv7gGlQ9KykTO9HopkbSY523nWOeGf9Ett5mbZS2KCbTAKAL8vAzYQXiIWycsUQEUUJhHAPDbVZRsC6OM7yFN+dvTNUmr/zf1bMIRGJDEDRzmsPv6qK30amx1qpUUYXUC3nfYg/ONM2t4l0j6U+xYB67GkUmymw+cYyH3+XXkm8FFC3L057G4VEhsTQqgcSkTQsnCEJXGj4UITRMjv9MuJ7+PAmQ2yt0otC0UCe2DLNo5JQ9KJSNIJU461X9EVAliSKrXKi1DwqZypSqtLUPCLQ3/S4bc1XUrevYcLT+ytDNfddqQBGLFVnOiyO2Ed82EW1/aBJeZCNwTijtrT/+BYvdJ8I28u6h8vGYI2Af97Tb5yaiHgWqIkSS9W99pG7oapd0BMqSrT4mHIl3yj710VojiPjebytoJLsy5B6wi545kBTCYwvhrW/AttEqXZoijRZNTK1VVgpg8kP4E3oejeADEgyJIOW9HiqTXadAgNHB9/V8+DpuCTyvoyTFRkcS6MiO11X0bh+r+hKb9FfHHAoZXOQkxwapL+DYnmC5IGViX4CwlpUUhTDpYUwHgVPwsy9JkRqvT0MyMFl1LBROBgWwV46OUAor5VcqxuVNJ0MSOlv8XbdRKE/GWpSGNgAqwdN9FhyHJSW2k9H28DprRHfg90jAw9WMYjmhPFajFjBNwJKvvJijIEITeiCc0JFhzgnb4IZ1tWuT5CKpTeoqq0LPjx5MdbbLaelVOLvEoT0Vcd+i2W+6BQqnBiUbCjNJipOFPiBqQwr/Ezc5wRU6Sh/t2aeSyv3yoGmqUn64S/6kmeieeZUiXHYsXGLnLIcRxvNtPgkQw1pMkoYOSg/yfxMv4340c5fOZ4lBc7V2s/N964Wk8NncFrH5K8S9S1AEMIKMe16SL+eDYrO9kLGyMzZmKtjcEgWRxzxSzd8bdWLequpAMMMJO8WR6mEgQT1SPtzBcjjHQ+behg+ZXmhUWGsUqBhQpHPVCHz3LCrxw7aVWPEHMl/hcCDo1R3LUJTS2FHQm18Z9BhHRbHUfbGxRPSGtSJSQvzAf60Doa0gEMwDAP7gQrU0HgNiIum1XPmpjPAepEttJblNIVFYK8I5kWsIbH5VCAEfEPmFV7ZBeNOKnN1oewSBKOQ8nsiDJwh5SuTsWpU827tUHz5KbS1cC5ez0sdKmW8CT7Y/SEgR4GB3+d4KtTPGq9sZ9LoW7r0Oi4LFJS4j0hS74QMjU1TBI9Xp4xiGA28XBOAbj4YSDh+QV+fUgiElqwfNxIAHVWYSGycAbg5ckU4j8IfYQPDTQ3ts8jhQuQwbymsqaQN2Bf2JFB4l68zO7QrkcCyAnpuk1oI2dMoZ68jZy9XixKy9CuCuzeBDBWYmBbetoicswWQ98SjDCn5MsoUpmb7Fo26GYRIp26TrE0FcLG5MWwJFEDmGqPZ1eQ9oGQFj1XDYhRKb4YKCnXbTR2o6i2n+S20vyyWdj4RL6/2VAKANF4lEx6tIrJseu"

    print("=== EMPTY BUILD ===")
    empty_dict = decode_build(EMPTY_BUILD)
    print(json.dumps(empty_dict, indent=2, ensure_ascii=False))

    print("\n=== NORMAL BUILD ===")
    normal_dict = decode_build(NORMAL_BUILD)
    Path("normal_build.json").write_text(
        json.dumps(normal_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("Saved to normal_build.json")

    reencoded = encode_build(normal_dict)
    print("Re-encoded prefix:", reencoded[:40])

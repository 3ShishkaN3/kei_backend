import grpc
from django.conf import settings

from . import recognition_pb2
from . import recognition_pb2_grpc


class KanjiRecognitionService:
    def __init__(self, target: str | None = None):
        self._target = target or getattr(settings, 'KANJI_PAD_GRPC_ADDR', 'kanji-pad-grpc:50051')

    def recognize(self, strokes: list[list[list[float]]], top_n: int = 5) -> list[dict]:
        channel = grpc.insecure_channel(self._target)
        stub = recognition_pb2_grpc.RecognitionServiceStub(channel)

        request = recognition_pb2.RecognitionRequest(top_n=top_n)
        for stroke in strokes:
            grpc_stroke = request.normalized_strokes.add()
            for point in stroke:
                if len(point) != 2:
                    continue
                grpc_stroke.points.add(x=float(point[0]), y=float(point[1]))

        response = stub.Recognize(request, timeout=getattr(settings, 'KANJI_PAD_GRPC_TIMEOUT_SECONDS', 3.0))

        return [
            {
                'character': r.character,
                'distance': r.distance,
                'confidence': r.confidence,
            }
            for r in response.results
        ]

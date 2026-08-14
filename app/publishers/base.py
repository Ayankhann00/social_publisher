from abc import ABC, abstractmethod


class PublishResult:
    def __init__(self, external_post_id: str, replayed: bool = False):
        self.external_post_id = external_post_id
        self.replayed = replayed


class PublishError(Exception):
    pass


class SocialPublisher(ABC):
    @abstractmethod
    def publish(self, post) -> PublishResult:
        raise NotImplementedError

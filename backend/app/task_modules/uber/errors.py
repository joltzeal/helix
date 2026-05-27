from __future__ import annotations


class UberWorkflowError(RuntimeError):
    retryable = False


class RetryableStepError(UberWorkflowError):
    retryable = True


class FatalStepError(UberWorkflowError):
    retryable = False


class CleanupProfileError(FatalStepError):
    pass


class BrowserDisconnectedError(FatalStepError):
    pass


class ElementNotFoundError(RetryableStepError):
    pass


class ElementActionError(RetryableStepError):
    pass


class PageBlockedError(FatalStepError):
    pass


class AccountConfigError(FatalStepError):
    pass

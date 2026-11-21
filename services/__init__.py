"""
The Service classes (Part 1, Figure 4.5) hold the business logic.

When the pseudocode says  DISPLAY "message" / RETURN failure  the Python
code raises a ServiceError("message"). The route that called the service
catches it and shows the message to the user.
"""


class ServiceError(Exception):
    """A business rule was broken - the message is safe to show to the user."""
    pass

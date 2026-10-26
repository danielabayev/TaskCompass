"""Use cases after the interview: estimate, execution, retrospective, reports.

Each service changes the database in short transactions and raises FlowError
(with a Hebrew message) when a request does not fit the task's state.
"""

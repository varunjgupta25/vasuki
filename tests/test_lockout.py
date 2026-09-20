from app.services.intruder_detection_service import record_failure, is_locked_out

record_failure(0.5)
record_failure(0.4)
locked, remaining = record_failure(0.3)
print('Locked:', locked, 'Remaining:', remaining)

locked2, rem2 = is_locked_out()
print('DB check - Still locked:', locked2, 'Remaining:', rem2)
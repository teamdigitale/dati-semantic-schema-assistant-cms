import { TestBed } from '@angular/core/testing';

import { GlobalLoader } from './global-loader';

describe('GlobalLoader', () => {
  let service: GlobalLoader;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(GlobalLoader);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});

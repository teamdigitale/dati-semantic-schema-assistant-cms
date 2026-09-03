import { ComponentFixture, TestBed } from '@angular/core/testing';

import { GlobalSpinner } from './global-spinner';

describe('GlobalSpinner', () => {
  let component: GlobalSpinner;
  let fixture: ComponentFixture<GlobalSpinner>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [GlobalSpinner]
    })
    .compileComponents();

    fixture = TestBed.createComponent(GlobalSpinner);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
